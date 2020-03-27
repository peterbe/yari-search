# yari-search

An experiment to handle the indexing of built Yari content into Elasticsearch.

## To install

    poetry install

Installing and setting up Elasticsearch is outside the remit of this.

## To run

You need to have built Yari fully. Then you can run:

    poetry run yari-search index /path/to/yari/client/build

You can test the searching too:

    poetry run yari-search search "css"

To specify where Elasticsearch is you use either:

    poetry run yari-search --hosts=localhost:9999 search "food"

Or, the environment variable:

    export YARI_SEARCH_HOSTS=localhost:9201,localhost:9202
    poetry run yari-search search "food"

If you don't specify a `--hosts` or `YARI_SEARCH_HOSTS` it will assume `localhost:9200`.

## Update vs. starting over

When indexing, if you don't use the `--update` flag, it will first **delete
the index** and create it again. So, if the indexing is taking a very long time
you get some downtime in your search. However, unless you delete and re-create
the index you won't pick up the renames so you'll get 2 entries in Elasticsearch
if a slug has changed since the last indexing.

If you use:

    poetry run yari-search index --update /path/to/yari/client/build

it will do everything else, just won't recreate the index first.
