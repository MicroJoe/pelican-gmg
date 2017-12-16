# Almost completly copied from https://github.com/haum/pelican-flickrtag, but
# using GNU MediaGoblin instead of Flickr, and using GMG's title and description
# for generating text in figures.

import logging
import re
import pickle

import requests
from requests_oauthlib import OAuth1Session
from pelican import signals


# Public of GMG images looks like an UUID
GMG_REGEX = re.compile(
    r'(\[gmg:id\='
    r'([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}'
    r'-[0-9a-f]{12})\])')

logger = logging.getLogger(__name__)

tmp_file = './tmp_gmg'


def session(settings):
    return OAuth1Session(
        settings['GMG_API_CLIENT_KEY'],
        client_secret=settings['GMG_API_CLIENT_SECRET'],
        resource_owner_key=settings['GMG_API_RESOURCE_OWNER_KEY'],
        resource_owner_secret=settings['GMG_API_RESOURCE_OWNER_SECRET'])


def setup_gmg(generator):
    pass


def fetch_image(generator, public_id):
        base_url = generator.settings['GMG_API_BASE_URL']
        json = session(generator.settings) \
            .get(f'{base_url}/api/image/{public_id}/') \
            .json()

        logger.info(f"[gmg]: retrieving image {public_id}")

        medium_url = json["fullImage"]["url"].replace(".jpg", ".medium.jpg")
        medium = requests.head(medium_url)
        if medium.status_code == 404:
            medium_url = json["fullImage"]["url"]

        return {
            "url": json["fullImage"]["url"],
            "medium": medium_url,
            "name": json["displayName"],
            "content": json["content"],
        }


def replace_article_tags(generator):
    matches = []

    items = generator.articles
    for item in items:
        for match in GMG_REGEX.findall(item._content):
            matches.append(match[1])

    logger.info("[gmg]: Found {} photos".format(len(matches)))

    # Create a set of all found IDs
    photo_ids = set([])
    for public_id in matches:
        photo_ids.add(public_id)

    # Retrieve photos_mapping dict from cache pickle file if possible
    try:
        with open(tmp_file, 'rb') as f:
            photos_mapping = pickle.load(f)
    except (IOError, EOFError):
        photos_mapping = {}
    else:
        # Get the difference of photos_ids and what have been cached
        cached_ids = set(photos_mapping.keys())
        photo_ids = list(set(photo_ids) - cached_ids)

    # Fetch the images we have to fetch that have not been cached yet
    if photo_ids:
        for public_id in photo_ids:
            photos_mapping[public_id] = fetch_image(generator, public_id)

    # Save the photos_mapping for cache for next generation
    with open(tmp_file, 'wb') as f:
        pickle.dump(photos_mapping, f)

    from jinja2 import Template
    template = Template("""
        <div class="figure">
            <a href="{{ url }}">
                <img src="{{ medium }}" alt="{{ name }}" />
            </a>
            <p class="caption">{{ content }}</p>
        </div>
    """)

    for item in items:
        for match in GMG_REGEX.findall(item._content):
            public_id = match[1]
            context = generator.context.copy()
            context.update(photos_mapping[public_id])

            replacement = template.render(context)
            item._content = item._content.replace(match[0], replacement)


def register():
    signals.initialized.connect(setup_gmg)
    signals.article_generator_finalized.connect(replace_article_tags)
