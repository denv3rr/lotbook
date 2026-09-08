from modules.market_data.theaters import headlines_from_items, match_theaters


def test_match_theaters_ukraine_and_myanmar():
    europe = match_theaters(["Kyiv reports strikes in Ukraine"], parent_region="Europe")
    assert [item.theater_id for item in europe] == ["ukraine"]
    asia = match_theaters(["Myanmar junta clashes in Rakhine"], parent_region="Asia-Pacific")
    assert [item.theater_id for item in asia] == ["myanmar"]
    assert match_theaters(["European shipping disruption"], parent_region="Europe") == []


def test_match_theaters_uses_word_boundaries_for_short_aliases():
    assert match_theaters(["Somalia security situation"], parent_region="Africa") == []
    sahel = match_theaters(["Mali security situation"], parent_region="Africa")
    assert [item.theater_id for item in sahel] == ["sahel"]


def test_headlines_from_items_keeps_real_titles():
    rows = headlines_from_items(
        [
            {"title": "Kyiv reports overnight strikes", "source": "Reuters"},
            {"title": "", "source": "Skip"},
            {"title": "Second headline", "source": "AP"},
        ]
    )
    assert rows[0]["title"] == "Kyiv reports overnight strikes"
    assert rows[0]["source"] == "Reuters"
    assert len(rows) == 2
