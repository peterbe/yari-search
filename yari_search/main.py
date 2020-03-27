import time
import json
from pathlib import Path

import click
from elasticsearch_dsl.connections import connections
from elasticsearch.helpers import streaming_bulk

from yari_search import models


@click.group()
@click.option("--hosts", envvar="YARI_SEARCH_HOSTS", default="localhost:9200")
def main(hosts):
    """Main CLI for yari-search"""
    hosts = [x.strip() for x in hosts.split(",") if x.strip()]
    connections.create_connection(hosts=hosts)


@main.command()
@click.option("--autocomplete", is_flag=True)
@click.argument("text")
def search(text, autocomplete=False):
    """Search with the CLI"""
    # print(repr(text))

    s = models.Doc.search()
    s = s.suggest("title_suggestions", text, completion={"field": "title_suggest"})
    t0 = time.time()
    response = s.execute()
    t1 = time.time()
    for result in response.suggest.title_suggestions:
        for i, option in enumerate(result.options):
            if not i:
                print(f"Suggestions for {result.text}:")
            print(f"\t{option.text}", option._score)

    s = models.Doc.search()
    # s = s.query("match", title_suggest=text)
    # s = s.query("match", title=text)
    s = s.query("multi_match", query=text, fields=["title", "body"])
    # s = s.query("match_phrase", body=text)

    s = s.sort("-popularity", "_score")
    # s = s.sort("-popularity")

    t0 = time.time()
    response = s.execute()
    t1 = time.time()
    our_took = t1 - t0
    click.echo(
        f"{response.hits.total.value:,} pages found in took {our_took * 1000:.1f}ms"
    )
    for hit in response:
        # If you use '_score' in your `.sort()` (e.g. `s.sort("-popularity", "_score")`)
        # then you can use `hit.meta.score`. Or, if you don't specify a `.sort()`
        # at all.

        click.echo(
            f"{hit.title:<50}"
            # repr(hit.title).ljust(50),
            f"{hit.slug:<70}"
            f"{round(hit.popularity, 6)}",
        )


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
        title_suggest=doc["title"],
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
