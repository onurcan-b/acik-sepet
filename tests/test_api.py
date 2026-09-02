from acik_sepet.api import search_products


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"content": [{"id": "a", "title": "Yerli Muz 1 Kg"}]}


class FakeSession:
    def __init__(self):
        self.payloads = []

    def post(self, _url, *, headers, json, timeout):
        self.payloads.append(json)
        return FakeResponse()


def test_search_sends_market_category_filter():
    session = FakeSession()
    rows = search_products(
        "muz kg",
        category_level="sub_category",
        category_values=["Muz"],
        session=session,
    )
    assert [row["id"] for row in rows] == ["a"]
    assert session.payloads == [{"keywords": "muz kg", "pages": 0, "size": 25, "sub_category": ["Muz"]}]
    assert rows[0]["_query_category_level"] == "sub_category"
    assert rows[0]["_query_category_values"] == ["Muz"]
