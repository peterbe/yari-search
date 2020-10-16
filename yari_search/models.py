from elasticsearch_dsl import (
    Document,
    Float,
    Keyword,
    Boolean,
    # SearchAsYouType,
    Text,
    analyzer,
    # token_filter,
)

# Reminder!! If you debug analyzers with the (sample) command:
#
#    poetry run yari-search analyze text_analyzer "<video>"
#
# But remember, you have to re-index before any edits here take effect.

text_analyzer = analyzer(
    "text_analyzer",
    tokenizer="standard",
    # The "asciifolding" token filter makes it so that
    # typing "bézier" becomes the same as searching for "bezier"
    # https://www.elastic.co/guide/en/elasticsearch/reference/7.9/analysis-asciifolding-tokenfilter.html
    filter=["lowercase", "stop", "asciifolding"],
    # char_filter=["html_strip"],
)

html_text_analyzer = analyzer(
    "html_text_analyzer",
    tokenizer="standard",
    filter=["lowercase", "asciifolding", "stop", "snowball"],
    # It's important that you don't use `char_filter=["html_strip"]`
    # on the titles. For example, there are titles like `<video>`.
    # If you do `GET /_analyze` on that with or without the html_strip
    # char filter is the difference between getting `["video"]` and `[]`.
)


class Doc(Document):
    title = Text(required=True, analyzer=html_text_analyzer)
    # title_autocomplete = SearchAsYouType(max_shingle_size=3)
    body = Text(analyzer=text_analyzer)
    locale = Keyword()
    archived = Boolean()
    slug = Keyword()
    popularity = Float()

    class Index:
        name = "yari_doc"
