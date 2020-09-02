from elasticsearch_dsl import (
    Document,
    Float,
    Keyword,
    # SearchAsYouType,
    Text,
    analyzer,
    # token_filter,
)

text_analyzer = analyzer(
    "text_analyzer",
    tokenizer="standard",
    filter=["lowercase", "stop", "snowball"],
    # filter=["lowercase", "snowball"],
    char_filter=["html_strip"],
)

# my_custom_html_strip_char_filter = token_filter(
#     "my_custom_html_strip_char_filter",
#     type="html_strip",
#     escaped_tags=["b", "a", "em", "i", "p"],
# )


html_text_analyzer = analyzer(
    "html_text_analyzer",
    tokenizer="standard",
    # filter=["lowercase", "stop", "snowball"],
    filter=["lowercase", "snowball"],
    # char_filter=[my_custom_html_strip_char_filter],
)


class Doc(Document):
    title = Text(required=True, analyzer=html_text_analyzer)
    # title_autocomplete = SearchAsYouType(max_shingle_size=3)
    body = Text(analyzer=text_analyzer)
    locale = Keyword()
    slug = Keyword()
    popularity = Float()

    class Index:
        name = "yari_doc"
