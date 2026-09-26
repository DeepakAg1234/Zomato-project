"""Streamlit demo for dataset-grounded restaurant recommendations."""

from __future__ import annotations

import logging

import streamlit as st
from pydantic import ValidationError

from src.models import RecommendationResponse, UserPreferences
from src.services.recommend import recommend
from src.store.restaurant_store import RestaurantStore, StoreNotReadyError
from src.ui.presentation import RestaurantCard, to_restaurant_card

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Bengaluru Restaurant Finder",
    page_icon="🍽️",
    layout="wide",
)


@st.cache_resource(show_spinner="Loading the restaurant catalogue…")
def load_store() -> RestaurantStore:
    """Load parquet and facets once for the Streamlit process."""
    return RestaurantStore.load()


def render_card(card: RestaurantCard) -> None:
    """Render a ranked restaurant result using display-safe fields only."""
    with st.container(border=True):
        title, rating = st.columns([5, 1])
        title.subheader(f"{card.rank}. {card.name}")
        rating.markdown(f"**{card.rating}**")

        details = f"{card.cuisines} · {card.cost}"
        if card.locality:
            details += f" · {card.locality}"
        st.caption(details)

        if card.badges:
            st.caption("  ·  ".join(f"✓ {badge}" for badge in card.badges))

        st.write(card.explanation)


def render_response(response: RecommendationResponse) -> None:
    """Render transparency notices and either results or the empty state."""
    if response.engine == "fallback":
        st.warning(
            "AI ranking is temporarily unavailable. These results use ratings, "
            "popularity, and preference fit."
        )
    if response.relaxation_applied:
        st.info(f"Search expanded: {response.relaxation_applied}")

    if not response.results:
        st.subheader("No matching restaurants found")
        st.write(response.message or "Try relaxing one or more filters.")
        st.caption(
            "Try a lower minimum rating, another budget, fewer cuisines, "
            "or a city-wide search."
        )
        return

    st.success(
        response.summary
        or "Here are the strongest matches for your selected preferences."
    )

    st.subheader(f"Top {len(response.results)} recommendations")
    for item in response.results:
        render_card(to_restaurant_card(item))


st.title("Find your next Bengaluru restaurant")
st.write(
    "Choose what matters to you. We shortlist from the local restaurant dataset, "
    "then use AI to rank and explain the best matches."
)

try:
    store = load_store()
except StoreNotReadyError as exc:
    st.error("The restaurant catalogue is not ready.")
    st.code(str(exc))
    st.stop()
except Exception:
    logger.exception("Could not load restaurant store")
    st.error("The restaurant catalogue could not be loaded. Please try again.")
    st.stop()

facets = store.facets
localities = list(facets.get("localities", []))
city_zones = list(facets.get("city_zones", []))
cuisines = list(facets.get("cuisines", []))

st.caption(f"Searching {len(store):,} restaurants from the Bengaluru dataset")

with st.form("preference_form", clear_on_submit=False):
    st.subheader("Your preferences")
    area_left, area_right = st.columns(2)
    with area_left:
        locality = st.selectbox(
            "Locality",
            [None, *localities],
            format_func=lambda value: "Any locality" if value is None else value,
            help="All options come from the restaurant dataset.",
        )
    with area_right:
        city_zone = st.selectbox(
            "City zone",
            [None, *city_zones],
            format_func=lambda value: "Any city zone" if value is None else value,
            help="Choose a broader zone, or combine it with a locality.",
        )

    preference_left, preference_right = st.columns(2)
    with preference_left:
        budget = st.segmented_control(
            "Budget",
            options=["low", "medium", "high"],
            default="medium",
            format_func=str.title,
            selection_mode="single",
        )
        selected_cuisines = st.multiselect(
            "Cuisines",
            cuisines,
            placeholder="Any cuisine",
            help="Select one or more cuisines from the dataset.",
        )
    with preference_right:
        min_rating = st.slider(
            "Minimum rating",
            min_value=0.0,
            max_value=5.0,
            value=4.0,
            step=0.1,
        )
        max_results = st.slider(
            "Number of recommendations",
            min_value=3,
            max_value=5,
            value=5,
        )

    extra_preferences = st.text_area(
        "Anything else?",
        max_chars=300,
        placeholder="e.g. family-friendly, quick service, good for a date",
        help="AI uses this only to rank and explain restaurants in the shortlist.",
    )

    is_recommending = bool(st.session_state.get("_recommendation_in_progress", False))
    submitted = st.form_submit_button(
        "Find restaurants",
        type="primary",
        disabled=is_recommending,
        use_container_width=True,
    )

if submitted and not is_recommending:
    st.session_state["_recommendation_in_progress"] = True
    try:
        preferences = UserPreferences(
            locality=locality,
            city_zone=city_zone,
            any_area=locality is None and city_zone is None,
            budget=budget or "medium",
            cuisines=selected_cuisines,
            min_rating=min_rating,
            extra_preferences=extra_preferences,
            max_results=max_results,
        )
        with st.spinner("Finding and ranking your best matches…"):
            st.session_state["recommendation_response"] = recommend(store, preferences)
        st.session_state.pop("recommendation_error", None)
    except ValidationError as exc:
        st.session_state["recommendation_error"] = str(exc)
        st.session_state.pop("recommendation_response", None)
    except Exception:
        logger.exception("Recommendation request failed")
        st.session_state["recommendation_error"] = (
            "Something went wrong while finding recommendations. Please try again."
        )
        st.session_state.pop("recommendation_response", None)
    finally:
        st.session_state["_recommendation_in_progress"] = False

if error := st.session_state.get("recommendation_error"):
    st.error(error)
elif response := st.session_state.get("recommendation_response"):
    render_response(response)
else:
    st.info(
        "Set your preferences and select **Find restaurants** to see grounded "
        "recommendations."
    )

