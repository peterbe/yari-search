from elasticsearch_dsl import (
    Completion,
    # Date,
    Document,
    Float,
    # Integer,
    Keyword,
    Text,
    analyzer,
)

html_strip = analyzer(
    "html_strip",
    tokenizer="standard",
    filter=["standard", "lowercase", "stop", "snowball"],
    char_filter=["html_strip"],
)


class Doc(Document):
    title = Text()
    title_suggest = Completion()
    body = Text()
    locale = Keyword()
    slug = Keyword()
    popularity = Float()

    class Index:
        name = "yari_doc"
        # settings = {
        #   "number_of_shards": 2,
        # }

    # def save(self, ** kwargs):
    #     self.lines = len(self.body.split())
    #     return super(Article, self).save(** kwargs)

    # def is_published(self):
    #     return datetime.now() >= self.published_from
