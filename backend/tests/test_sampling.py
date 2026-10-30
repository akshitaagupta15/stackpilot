from app.benchmark.dataset import load_dataset
from app.benchmark.run import select_items


def test_every_mixes_languages_and_limit_caps():
    items, _ = load_dataset()
    s = select_items(items, every=4)
    assert len(s) == 10 and {i["language"] for i in s} == {"en", "hi"}
    assert len(select_items(items, limit=3)) == 3
    assert len(select_items(items, limit=5, every=4)) == 5
    assert select_items(items) == items
