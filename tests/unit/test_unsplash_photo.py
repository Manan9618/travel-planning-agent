import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from travel_agent.tools.unsplash_photo import CoverPhoto, UnsplashPhotoTool

SEARCH_URL = "https://api.unsplash.com/search/photos"


def _photo_body(
    url="https://images.unsplash.com/photo-1",
    thumb_url="https://images.unsplash.com/photo-1-thumb",
    name="Jane Doe",
    profile="https://unsplash.com/@jane",
):
    return {
        "results": [
            {
                "urls": {"regular": url, "thumb": thumb_url},
                "user": {"name": name, "links": {"html": profile}},
            }
        ]
    }


def _tool(fake_cache, access_key="test-key"):
    return UnsplashPhotoTool(access_key=access_key, cache=fake_cache)


# --- no key configured -------------------------------------------------


def test_no_access_key_returns_none_without_any_request(fake_cache):
    tool = UnsplashPhotoTool(access_key="", cache=fake_cache)
    assert tool.get_cover_photo("Paris") is None


# --- happy path ----------------------------------------------------------


@responses.activate
def test_returns_cover_photo_on_success(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    photo = _tool(fake_cache).get_cover_photo("Paris")
    assert isinstance(photo, CoverPhoto)
    assert photo.url == "https://images.unsplash.com/photo-1"
    assert photo.photographer_name == "Jane Doe"
    assert photo.photographer_url == "https://unsplash.com/@jane"


@responses.activate
def test_sends_authorization_header(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    _tool(fake_cache, access_key="my-key").get_cover_photo("Paris")
    assert responses.calls[0].request.headers["Authorization"] == "Client-ID my-key"


# --- graceful fallbacks -------------------------------------------------


@responses.activate
def test_empty_results_returns_none(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json={"results": []}, status=200)
    assert _tool(fake_cache).get_cover_photo("Nowhereville") is None


@responses.activate
def test_connection_error_returns_none(fake_cache):
    responses.add(responses.GET, SEARCH_URL, body=RequestsConnectionError("down"))
    assert _tool(fake_cache).get_cover_photo("Paris") is None


@responses.activate
def test_malformed_response_returns_none(fake_cache):
    responses.add(
        responses.GET, SEARCH_URL, json={"results": [{"unexpected": "shape"}]}, status=200
    )
    assert _tool(fake_cache).get_cover_photo("Paris") is None


@responses.activate
def test_server_error_returns_none(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json={}, status=500)
    assert _tool(fake_cache).get_cover_photo("Paris") is None


# --- caching -------------------------------------------------------------


@responses.activate
def test_successful_lookup_is_cached(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    tool = _tool(fake_cache)
    tool.get_cover_photo("Paris")
    tool.get_cover_photo("Paris")
    assert len(responses.calls) == 1


@responses.activate
def test_empty_result_is_also_cached_as_none(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json={"results": []}, status=200)
    tool = _tool(fake_cache)
    assert tool.get_cover_photo("Nowhereville") is None
    assert tool.get_cover_photo("Nowhereville") is None
    assert len(responses.calls) == 1


# --- get_photo (generalized per-query lookup, e.g. per-attraction) -------


@responses.activate
def test_get_photo_sends_the_raw_query_unmodified(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    _tool(fake_cache).get_photo("Eiffel Tower Paris")
    assert responses.calls[0].request.params["query"] == "Eiffel Tower Paris"


@responses.activate
def test_get_photo_returns_regular_size_by_default(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    photo = _tool(fake_cache).get_photo("Eiffel Tower Paris")
    assert photo.url == "https://images.unsplash.com/photo-1"


@responses.activate
def test_get_photo_returns_thumb_size_when_requested(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    photo = _tool(fake_cache).get_photo("Eiffel Tower Paris", thumbnail=True)
    assert photo.url == "https://images.unsplash.com/photo-1-thumb"


@responses.activate
def test_get_photo_regular_and_thumb_are_cached_separately(fake_cache):
    responses.add(responses.GET, SEARCH_URL, json=_photo_body(), status=200)
    tool = _tool(fake_cache)
    tool.get_photo("Eiffel Tower Paris")
    tool.get_photo("Eiffel Tower Paris", thumbnail=True)
    assert len(responses.calls) == 2


@responses.activate
def test_get_photo_without_access_key_returns_none(fake_cache):
    tool = UnsplashPhotoTool(access_key="", cache=fake_cache)
    assert tool.get_photo("Eiffel Tower Paris") is None
