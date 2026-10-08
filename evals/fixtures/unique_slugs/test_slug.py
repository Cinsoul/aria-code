"""Every product needs its own URL, and Chinese titles are most of them."""

import pytest

from slug import slugify, unique_slugs


def test_ascii_title():
    assert slugify("Blue Mug 350ml") == "blue-mug-350ml"


def test_accents_are_dropped():
    assert slugify("Café Crème") == "cafe-creme"


def test_chinese_is_kept():
    assert slugify("保温杯 500ml") == "保温杯-500ml"


def test_nothing_left_is_an_error():
    with pytest.raises(ValueError):
        slugify("!!!")


def test_repeats_are_numbered():
    assert unique_slugs(["Mug", "mug!", "Mug"]) == ["mug", "mug-2", "mug-3"]


def test_a_number_never_collides_with_a_real_title():
    # "Mug 2" really is called mug-2, so the second "Mug" cannot be.
    assert unique_slugs(["Mug 2", "Mug", "Mug"]) == ["mug-2", "mug", "mug-3"]
