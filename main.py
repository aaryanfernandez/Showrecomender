import os
import json
import streamlit as st
from dotenv import load_dotenv
import tmdbsimple as tmdb

load_dotenv()
tmdb.API_KEY = os.getenv("TMDB_API_KEY")

HISTORY_FILE = "watch_history.json"

st.set_page_config(page_title="showrecomender",
                   page_icon="🎬", layout="centered")


# ---------- Genre setup (cached so it only hits the API once per session) ----------

@st.cache_data
def load_genre_maps():
    genres_movie = tmdb.Genres().movie_list()["genres"]
    genres_tv = tmdb.Genres().tv_list()["genres"]
    movie_map = {g["id"]: g["name"] for g in genres_movie}
    tv_map = {g["id"]: g["name"] for g in genres_tv}
    return movie_map, tv_map


MOVIE_GENRE_MAP, TV_GENRE_MAP = load_genre_maps()


def get_genre_sentence(genre_ids_list, genre_map):
    gen = [genre_map.get(gid, "Unknown") for gid in genre_ids_list]
    if not gen:
        return ""
    elif len(gen) == 1:
        return gen[0]
    elif len(gen) == 2:
        return f"{gen[0]} and {gen[1]}"
    else:
        return f"{', '.join(gen[:-1])} and {gen[-1]}"


@st.cache_data
def get_item_details(tmdb_id, media_type):
    """Fetch poster_path for a history entry (cached to avoid refetching every rerun)."""
    try:
        if media_type == "movie":
            response = tmdb.Movies(tmdb_id).info()
        else:
            response = tmdb.TV(tmdb_id).info()
        return response.get("poster_path")
    except Exception:
        return None


# ---------- History persistence ----------

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)


def add_history(item):
    history = load_history()

    tmdb_id = item.get("id")
    media_type = item.get("media_type")
    title = item.get("title") or item.get("name")
    genre_ids = item.get("genre_ids", [])

    already_watched = any(
        entry["tmdb_id"] == tmdb_id and entry["media_type"] == media_type
        for entry in history
    )
    if already_watched:
        st.warning(f"{title} is already in your watch history.")
        return

    entry = {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": title,
        "genre_ids": genre_ids,
    }
    history.append(entry)
    save_history(history)
    st.success(f"Added '{title}' to watch history.")


def remove_from_history(tmdb_id, media_type):
    """Remove an item from watch history."""
    history = load_history()
    history = [
        entry for entry in history
        if not (entry["tmdb_id"] == tmdb_id and entry["media_type"] == media_type)
    ]
    save_history(history)
    st.success("Removed from watch history.")


# ---------- Search ----------

def search_movie(movie_name):
    search = tmdb.Search()
    response = search.movie(query=movie_name)
    if not response["results"]:
        return None
    result = response["results"][0]
    result["media_type"] = "movie"
    return result


def search_show(show_name):
    search = tmdb.Search()
    response = search.tv(query=show_name)
    if not response["results"]:
        return None
    result = response["results"][0]
    result["media_type"] = "tv"
    return result


def display_result_card(item):
    media_type = item.get("media_type")
    title = item.get("title") or item.get("name")
    genre_map = MOVIE_GENRE_MAP if media_type == "movie" else TV_GENRE_MAP
    sentence = get_genre_sentence(item.get("genre_ids", []), genre_map)

    poster_path = item.get("poster_path")
    col1, col2 = st.columns([1, 2])
    with col1:
        if poster_path:
            st.image(f"https://image.tmdb.org/t/p/w300{poster_path}")
    with col2:
        st.subheader(title)
        st.caption(f"Genres: {sentence}" if sentence else "Genres: N/A")
        st.write(
            f"⭐ {item.get('vote_average', 0)} ({item.get('vote_count', 0)} votes)")
        st.write(item.get("overview", "No overview available."))


# ---------- Recommendations ----------

def get_top_genres(history, media_type, top_n=2):
    genre_counts = {}
    for entry in history:
        if entry["media_type"] != media_type:
            continue
        for genre_id in entry.get("genre_ids", []):
            genre_counts[genre_id] = genre_counts.get(genre_id, 0) + 1

    sorted_genres = sorted(genre_counts.items(),
                           key=lambda x: x[1], reverse=True)
    return [genre_id for genre_id, count in sorted_genres[:top_n]]


def get_recommendations(media_type="movie", top_n=5):
    history = load_history()
    if not history:
        return [], "No watch history yet — add something first to get recommendations."

    top_genres = get_top_genres(history, media_type)
    if not top_genres:
        return [], f"No {media_type} history to base recommendations on."

    watched_ids = {entry["tmdb_id"]
                   for entry in history if entry["media_type"] == media_type}

    discover = tmdb.Discover()
    genre_str = ",".join(str(g) for g in top_genres)

    if media_type == "movie":
        response = discover.movie(
            with_genres=genre_str, sort_by="popularity.desc")
    else:
        response = discover.tv(with_genres=genre_str,
                               sort_by="popularity.desc")

    recommendations = []
    for item in response["results"]:
        if item["id"] in watched_ids:
            continue
        item["media_type"] = media_type
        recommendations.append(item)
        if len(recommendations) == top_n:
            break

    genre_map = MOVIE_GENRE_MAP if media_type == "movie" else TV_GENRE_MAP
    reason = f"Because you've watched {get_genre_sentence(top_genres, genre_map)} {media_type}s"
    return recommendations, reason


# ---------- App state ----------

if "last_result" not in st.session_state:
    st.session_state.last_result = None

st.title("🎬 showrecomender")

tab_search, tab_recs, tab_history = st.tabs(
    ["Search", "Recommendations", "History"])


# ---------- Search tab ----------

with tab_search:
    media_choice = st.radio(
        "Looking for a:", ["Movie", "TV Show"], horizontal=True)
    query = st.text_input("Title")

    if st.button("Search", type="primary"):
        if not query.strip():
            st.warning("Enter a title to search.")
        else:
            result = search_movie(
                query) if media_choice == "Movie" else search_show(query)
            st.session_state.last_result = result
            if result is None:
                st.error(f"No results found for '{query}'.")

    if st.session_state.last_result:
        st.divider()
        display_result_card(st.session_state.last_result)
        if st.button("➕ Add to watch history"):
            add_history(st.session_state.last_result)


# ---------- Recommendations tab ----------

with tab_recs:
    rec_type = st.radio(
        "Recommend:", ["Movie", "TV Show"], horizontal=True, key="rec_type")
    media_type = "movie" if rec_type == "Movie" else "tv"

    if st.button("Get recommendations"):
        recs, reason = get_recommendations(media_type=media_type)
        if not recs:
            st.info(reason)
        else:
            st.caption(reason)
            for item in recs:
                display_result_card(item)
                st.divider()


# ---------- History tab ----------

with tab_history:
    history = load_history()
    if not history:
        st.info("No watch history yet.")
    else:
        st.subheader(f"Your Watch History ({len(history)} items)")
        for entry in history:
            col1, col2, col3 = st.columns([1, 2, 0.3])

            with col1:
                poster_path = get_item_details(
                    entry["tmdb_id"], entry["media_type"])
                if poster_path:
                    st.image(f"https://image.tmdb.org/t/p/w300{poster_path}")
                else:
                    st.write("No poster")

            with col2:
                genre_map = MOVIE_GENRE_MAP if entry["media_type"] == "movie" else TV_GENRE_MAP
                sentence = get_genre_sentence(
                    entry.get("genre_ids", []), genre_map)
                st.subheader(entry["title"])
                st.caption(f"{entry['media_type'].capitalize()}")
                st.write(
                    f"**Genres:** {sentence}" if sentence else "**Genres:** N/A")

            with col3:
                if st.button("🗑️", key=f"delete_{entry['tmdb_id']}_{entry['media_type']}"):
                    remove_from_history(entry["tmdb_id"], entry["media_type"])
                    st.rerun()

            st.divider()
