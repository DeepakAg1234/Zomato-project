from src.models import RecommendationItem
from src.ui.presentation import to_restaurant_card


def test_card_mapping_contains_required_display_fields():
    item = RecommendationItem(
        id="restaurant-1",
        rank=1,
        name="Trattoria Indira",
        cuisines=["Italian", "Pizza"],
        rating=4.5,
        votes=2000,
        cost_for_two=800,
        locality="Indiranagar",
        online_order=True,
        book_table=True,
        explanation="A highly rated Italian option that fits your budget.",
        url="https://example.test/private-from-card",
    )

    card = to_restaurant_card(item)

    assert card.rank == 1
    assert card.name == "Trattoria Indira"
    assert card.cuisines == "Italian, Pizza"
    assert card.rating == "4.5 ★"
    assert card.cost == "≈ ₹800 for two"
    assert card.locality == "Indiranagar"
    assert card.explanation == item.explanation
    assert card.badges == ("Table booking", "Online ordering")
    assert not hasattr(card, "url")


def test_card_mapping_handles_missing_optional_data():
    item = RecommendationItem(
        id="restaurant-2",
        rank=2,
        name="New Cafe",
        cuisines=[],
        rating=None,
        cost_for_two=None,
        locality="HSR",
        explanation="A nearby option.",
    )

    card = to_restaurant_card(item)

    assert card.cuisines == "Cuisine not listed"
    assert card.rating == "Not rated"
    assert card.cost == "Cost not listed"
    assert card.badges == ()
