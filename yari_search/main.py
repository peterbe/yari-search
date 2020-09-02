import json
import time
from pathlib import Path

import click
from elasticsearch.helpers import streaming_bulk
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl.query import MultiMatch

from yari_search import models


@click.group()
@click.option("--hosts", envvar="YARI_SEARCH_HOSTS", default="localhost:9200")
def main(hosts):
    """Main CLI for yari-search"""
    hosts = [x.strip() for x in hosts.split(",") if x.strip()]
    connections.create_connection(hosts=hosts)


@main.command()
@click.option("--show-highlights", is_flag=True)
@click.argument("text")
def search(text, show_highlights=False):
    """Search with the CLI"""
    # print(repr(text))

    s = models.Doc.search()
    s = s.suggest("title_suggestions", text, term={"field": "title"})
    s = s.suggest("body_suggestions", text, term={"field": "body"})
    t0 = time.time()
    response = s.execute()
    t1 = time.time()
    good_suggestions = []
    _good_suggestions = set()  # hash for uniqueness
    for result in response.suggest.title_suggestions:
        for i, option in enumerate(result.options):
            # if not i:
            #     print(f"Title Suggestions for {result.text}:")
            if option.score > 0.75 and option.text not in _good_suggestions:
                good_suggestions.append(option.text)
                _good_suggestions.add(option.text.lower())
    for result in response.suggest.body_suggestions:
        for i, option in enumerate(result.options):
            # if not i:
            #     print(f"Body Suggestions for {result.text}:")
            if option.score > 0.75 and option.text not in _good_suggestions:
                good_suggestions.append(option.text)
                _good_suggestions.add(option.text.lower())
            # print(f"\t{option.text}", option.score)

    if good_suggestions:
        click.echo(click.style("Did you mean...", bold=True))
        for suggestion in good_suggestions:
            click.echo(click.style(f"\t{suggestion}", fg="yellow") + "?")

    s = models.Doc.search()

    if show_highlights:
        # s = s.highlight_options(order="score")
        s = s.highlight_options(
            pre_tags=["<mark>"],
            post_tags=["</mark>"],
            number_of_fragments=4,
            fragment_size=80,
            encoder="html",
        )
        s = s.highlight("title")
        s = s.highlight("body")

    s = s.query("multi_match", query=text, fields=["title", "body"])

    s = s.sort("-popularity", "_score")
    # s = s.sort("-popularity")

    t0 = time.time()
    response = s.execute()
    t1 = time.time()
    our_took = t1 - t0
    click.echo(
        f"{response.hits.total.value:,} pages found in took {our_took * 1000:.1f}ms"
    )

    from colorama import Fore, Back, Style

    for hit in response:
        # If you use '_score' in your `.sort()` (e.g. `s.sort("-popularity", "_score")`)
        # then you can use `hit.meta.score`. Or, if you don't specify a `.sort()`
        # at all.

        click.echo(
            click.style(
                f"{hit.title:<50}"
                # repr(hit.title).ljust(50),
                f"{hit.slug:<70}",
                bold=True,
            )
            + f"{round(hit.popularity, 6)}",
        )

        if show_highlights:
            # for fragment in hit.meta.highlight.title:
            #     print("TITLE:", repr(fragment))
            for fragment in hit.meta.highlight.body:
                # print(repr(fragment))
                click.echo(
                    fragment.replace("<mark>", Back.LIGHTYELLOW_EX + Fore.BLACK)
                    .replace("</mark>", Style.RESET_ALL)
                    .strip()
                    .replace("\n", " ")
                )
            click.echo("")


@main.command()
@click.option("--update", is_flag=True)
@click.argument("buildroot", type=click.Path(exists=True))
def index(buildroot, update=False):
    """Yari build content from disk to Elasticsearch"""
    connection = connections.get_connection()
    health = connection.cluster.health()
    status = health["status"]
    if status not in ("green", "yellow"):
        raise click.ClickException(f"status {status} not green or yellow")

    count_todo = 0
    for file in walk(Path(buildroot)):
        count_todo += 1

    click.echo(f"Found {count_todo:,} documents to index")

    index = models.Doc._index
    if not update:
        index.delete(ignore=404)
        index.create()

    iterator = walk(Path(buildroot))
    count_done = 0
    t0 = time.time()
    with click.progressbar(length=count_todo, label="Indexing", width=0) as bar:
        for x in streaming_bulk(
            connection,
            (to_search(d).to_dict(True) for d in iterator),
            index="yari_docs",
        ):
            count_done += 1
            bar.update(1)
    t1 = time.time()
    click.echo(f"Took {t1-t0:.1f} seconds to index {count_done:,} documents")


def to_search(file):
    with open(file) as f:
        data = json.load(f)
    doc = data["doc"]
    locale, slug = doc["mdn_url"].split("/docs/", 1)
    locale = locale[1:]
    return models.Doc(
        _id=doc["mdn_url"],
        title=doc["title"],
        # title_suggest=doc["title"],
        body="\n".join(
            x["value"]["content"] for x in doc["body"] if x["type"] == "prose"
        ),
        popularity=doc["popularity"],
        slug=slug,
        locale=locale,
    )


def walk(root):
    for path in root.iterdir():
        if path.is_dir():
            for file in walk(path):
                yield file
        elif path.name == "index.json":
            yield path
