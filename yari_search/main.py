import json
import time
from pathlib import Path

import click
from pyquery import PyQuery as pq
from elasticsearch.helpers import streaming_bulk
from elasticsearch_dsl.connections import connections

# from elasticsearch_dsl.query import MultiMatch

from yari_search import models


@click.group()
@click.option("--hosts", envvar="YARI_SEARCH_HOSTS", default="localhost:9200")
def main(hosts):
    """Main CLI for yari-search"""
    hosts = [x.strip() for x in hosts.split(",") if x.strip()]
    connections.create_connection(hosts=hosts)


@main.command()
@click.argument("analyzer")
@click.argument("text")
def analyze(text, analyzer):
    index = models.Doc._index
    from pprint import pprint

    pprint(index.analyze(body={"text": text, "analyzer": analyzer}))


@main.command()
@click.option("--show-highlights", is_flag=True)
@click.option("--locale")
@click.option("--size", type=int)
@click.option("--debug", is_flag=True)
@click.argument("text")
def search(text, show_highlights=False, locale=None, debug=False, size=20):
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
            # print("TITLE", option.score, option.text)
            if option.score > 0.75 and option.text not in _good_suggestions:
                good_suggestions.append(option.text)
                _good_suggestions.add(option.text.lower())
    for result in response.suggest.body_suggestions:
        for i, option in enumerate(result.options):
            # if not i:
            #     print(f"Body Suggestions for {result.text}:")
            # print("BODY", option.score, option.text)
            if option.score > 0.75 and option.text not in _good_suggestions:
                good_suggestions.append(option.text)
                _good_suggestions.add(option.text.lower())
            # print(f"\t{option.text}", option.score)

    if good_suggestions:
        click.echo(click.style("Did you mean...", bold=True))
        for suggestion in good_suggestions:
            click.echo(click.style(f"\t{suggestion}", fg="yellow") + "?")

    s = models.Doc.search()

    if locale:
        s = s.filter("terms", locale=[locale.lower()])
        # s = s.filter("term", locale=locale)

    s = s.filter("term", archived=False)

    if show_highlights:
        # s = s.highlight_options(order="score")
        s = s.highlight_options(
            pre_tags=["<mark>"],
            post_tags=["</mark>"],
            number_of_fragments=3,
            fragment_size=80,
            # encoder="html",
        )
        s = s.highlight("title", "body")
        # s = s.highlight("body")

    s = s.query("multi_match", query=text, fields=["title", "body"])

    # s = s.sort("-popularity", "_score")
    # s = s.sort("archived", "_score", "-popularity")
    s = s.sort("_score", "-popularity")
    # s = s.sort("-popularity")

    # # only return the selected fields
    # s = s.source(['title', 'body'])
    # # don't return any fields, just the metadata
    # s = s.source(False)
    # # explicitly include/exclude fields
    # s = s.source(includes=["title"], excludes=["user.*"])
    s = s.source(excludes=["body"])
    # # reset the field selection
    # s = s.source(None)

    s = s[:size]

    if debug:
        from pprint import pprint

        print(json.dumps(s.to_dict(), indent=3))

    t0 = time.time()
    response = s.execute()
    t1 = time.time()
    our_took = t1 - t0
    click.echo(
        f"{response.hits.total.value:,} pages found in took {our_took * 1000:.1f}ms"
    )

    from colorama import Fore, Style

    for hit in response:
        # If you use '_score' in your `.sort()` (e.g. `s.sort("-popularity", "_score")`)
        # then you can use `hit.meta.score`. Or, if you don't specify a `.sort()`
        # at all.

        try:
            title_fragments = hit.meta.highlight.title
        except AttributeError:
            title_fragments = []

        title = (
            title_fragments
            and title_fragments[0]
            .replace("<mark>", Fore.LIGHTYELLOW_EX)
            .replace("</mark>", Style.RESET_ALL)
            or hit.title
        )
        click.echo(
            click.style(
                f"{hit.archived and Fore.RED + 'Archived' + Fore.RESET or ''} {title:<50}"
                f"{hit.slug:<70}",
                bold=True,
            )
            + f"{round(hit.popularity, 6)}",
        )

        if show_highlights:
            try:
                body_fragments = hit.meta.highlight.body
            except AttributeError:
                body_fragments = []
            for fragment in body_fragments:
                click.echo(
                    fragment.replace("<mark>", Fore.LIGHTYELLOW_EX)
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
        archived=doc["isArchive"],
        body=html_strip(
            "\n".join(
                x["value"]["content"]
                for x in doc["body"]
                if x["type"] == "prose" and x["value"]["content"]
            )
        ),
        popularity=doc["popularity"],
        slug=slug,
        locale=locale.lower(),
    )


def html_strip(text):
    text = text.strip()
    if not text:
        return ""
    return pq(text).text()


def walk(root):
    for path in root.iterdir():
        if path.is_dir():
            for file in walk(path):
                yield file
        elif path.name == "index.json":
            yield path
