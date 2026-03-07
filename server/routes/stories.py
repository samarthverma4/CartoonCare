"""
Story & Children Routes Blueprint
──────────────────────────────────
CRUD for stories and children profiles, story generation,
feedback, and personalization.
"""

import os
import json
import time
import logging
from urllib.parse import urlparse

import requests
from flask import Blueprint, request, jsonify, g

import database_v2 as db
from auth import login_required
from content_safety import validate_input, moderate_output, moderate_image_prompt, sanitize_html
from monitoring import usage_counter, AIGenerationTracker, perf_tracker
from prompt_manager import build_story_prompt, build_image_prompt

logger = logging.getLogger('brave_story.routes.stories')

stories_bp = Blueprint('stories', __name__)

# cloud storage is injected at registration time via init_app
_image_storage = None


def init_stories_bp(image_storage):
    """Inject the image storage backend so the blueprint can save images."""
    global _image_storage
    _image_storage = image_storage


def _refresh_image_urls(story):
    """Regenerate S3 presigned URLs for story page images.

    Stored presigned URLs expire after 7 days. This extracts the S3 key
    from stale URLs and generates fresh presigned URLs on every read.
    """
    if not _image_storage or not story:
        return story

    from cloud_storage import S3Storage
    if not isinstance(_image_storage, S3Storage):
        return story

    pages = story.get('pages')
    if isinstance(pages, str):
        try:
            pages = json.loads(pages)
        except (json.JSONDecodeError, TypeError):
            return story
    if not pages:
        return story

    changed = False
    for page in pages:
        url = page.get('imageUrl')
        if not url:
            continue
        # Extract the filename from the presigned URL
        filename = _extract_s3_filename(url)
        if filename:
            page['imageUrl'] = _image_storage.get_url(filename)
            changed = True

    if changed:
        story['pages'] = pages
    return story


def _extract_s3_filename(url):
    """Extract the image filename from a presigned S3 URL or local path."""
    if not url:
        return None
    # Full S3 presigned URL: https://bucket.s3.amazonaws.com/generated_images/file.png?...
    if 's3.amazonaws.com' in url or 's3.' in url:
        parsed = urlparse(url)
        path = parsed.path.lstrip('/')
        # Key is like "generated_images/story_123_1.png" → extract filename
        if 'generated_images/' in path:
            return path.split('generated_images/')[-1]
        return path
    # Local URL: /generated_images/file.png
    if url.startswith('/generated_images/'):
        return url.split('/generated_images/')[-1].split('?')[0]
    return None


# ── Children Profile Routes ──────────────────────────────────────────

@stories_bp.route('/api/children', methods=['GET'])
@login_required
def list_children():
    """List all children profiles belonging to the authenticated user."""
    return jsonify(db.get_children(g.user_id))


@stories_bp.route('/api/children', methods=['POST'])
@login_required
def add_child():
    """Create a new child profile.

    Expects JSON with ``name``, ``age``, and optionally ``gender``
    and ``conditions``.  Validates inputs server-side before saving.
    """
    data = request.get_json()

    # ── Server-side input validation ─────────────────────────────
    name = (data.get('name') or '').strip()
    age = data.get('age')
    gender = (data.get('gender') or 'neutral').strip()
    conditions = data.get('conditions', [])

    if not name or len(name) < 1 or len(name) > 50:
        return jsonify({'message': 'Child name must be 1-50 characters'}), 400
    if not isinstance(age, int) or age < 2 or age > 18:
        return jsonify({'message': 'Age must be an integer between 2 and 18'}), 400
    if gender not in ('male', 'female', 'neutral'):
        return jsonify({'message': 'Gender must be male, female, or neutral'}), 400
    if not isinstance(conditions, list) or len(conditions) > 10:
        return jsonify({'message': 'Conditions must be a list (max 10 items)'}), 400
    for c in conditions:
        if not isinstance(c, str) or len(c) > 200:
            return jsonify({'message': 'Each condition must be a string (max 200 chars)'}), 400

    # Sanitize text inputs before storage (XSS prevention)
    name = sanitize_html(name)
    conditions = [sanitize_html(c) for c in conditions]

    child = db.create_child(g.user_id, name, age, gender, conditions)
    return jsonify(child), 201


@stories_bp.route('/api/children/<int:child_id>', methods=['PUT'])
@login_required
def update_child(child_id):
    """Update an existing child profile by ID (only if owned by authenticated user)."""
    data = request.get_json()

    # Sanitize text fields before passing to DB (XSS prevention)
    if 'name' in data and isinstance(data['name'], str):
        data['name'] = sanitize_html(data['name'].strip())
    if 'conditions' in data and isinstance(data['conditions'], list):
        data['conditions'] = [sanitize_html(c) for c in data['conditions'] if isinstance(c, str)]

    child = db.update_child(child_id, user_id=g.user_id, **data)
    if not child:
        return jsonify({'message': 'Child not found'}), 404
    return jsonify(child)


@stories_bp.route('/api/children/<int:child_id>', methods=['DELETE'])
@login_required
def delete_child(child_id):
    """Delete a child profile by ID (only if owned by authenticated user)."""
    if not db.delete_child(child_id, user_id=g.user_id):
        return jsonify({'message': 'Child not found'}), 404
    return jsonify({'success': True})


# ── Story CRUD Routes ────────────────────────────────────────────────

@stories_bp.route('/api/stories', methods=['GET'])
@login_required
def list_stories():
    """Return stories belonging to the authenticated user."""
    stories = db.get_stories(user_id=g.user_id)
    return jsonify([_refresh_image_urls(s) for s in stories])


@stories_bp.route('/api/stories/favorites', methods=['GET'])
@login_required
def favorite_stories():
    """Return only favorite stories belonging to the authenticated user."""
    stories = db.get_favorite_stories(user_id=g.user_id)
    return jsonify([_refresh_image_urls(s) for s in stories])


@stories_bp.route('/api/stories/<int:story_id>', methods=['GET'])
@login_required
def get_story(story_id):
    """Retrieve a single story by ID (only if owned by authenticated user)."""
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(_refresh_image_urls(story))


@stories_bp.route('/api/stories/<int:story_id>', methods=['DELETE'])
@login_required
def delete_story(story_id):
    """Delete a story by ID (only if owned by authenticated user)."""
    deleted = db.delete_story(story_id, user_id=g.user_id)
    if not deleted:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify({'success': True, 'message': 'Story deleted successfully'})


@stories_bp.route('/api/stories/<int:story_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(story_id):
    """Toggle the favorite flag on a story (only if owned by authenticated user)."""
    story = db.toggle_favorite(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(story)


# ── Story Generation ─────────────────────────────────────────────────

@stories_bp.route('/api/stories/generate', methods=['POST'])
@login_required
def generate_story():
    """Generate a new story using Gemini + Flux 2 Pro.

    Accepts JSON with ``childName``, ``age``, ``gender``, ``condition``,
    ``heroCharacteristics``, and optional ``childId``.  Validates all
    inputs server-side before AI generation.
    """
    start_time = time.time()
    user_id = g.user_id

    try:
        data = request.get_json()
        child_name = (data.get('childName') or '').strip()
        age = int(data.get('age', 6))
        gender = (data.get('gender') or 'neutral').strip()
        condition = (data.get('condition') or '').strip()
        hero_characteristics = (data.get('heroCharacteristics') or '').strip()
        child_id = data.get('childId')

        # Custom story settings
        story_length = (data.get('storyLength') or '').strip()
        tone = (data.get('tone') or '').strip()
        theme = (data.get('theme') or '').strip()
        villain_type = (data.get('villainType') or '').strip()
        ending_type = (data.get('endingType') or '').strip()
        illustration_style = (data.get('illustrationStyle') or '').strip()
        reading_level = (data.get('readingLevel') or '').strip()

        # 0. Content safety: validate & moderate input
        valid, error = validate_input(child_name, age, condition, hero_characteristics)
        if not valid:
            logger.warning(f'Input validation failed: {error}')
            return jsonify({'message': error}), 400

        # Load personalization data if a child profile is linked
        preferences = []
        story_history = []
        if child_id:
            if not db.verify_child_owner(child_id, user_id):
                return jsonify({'message': 'Child profile not found'}), 404
            try:
                preferences = db.get_preferences(child_id)
                story_history = db.get_child_story_history(child_id)
            except Exception as e:
                logger.warning(f'Failed to load personalization: {e}')

        # 1. Generate story text with Gemini
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({'message': 'GEMINI_API_KEY not configured'}), 500

        import google.generativeai as genai

        genai.configure(api_key=gemini_key)  # type: ignore[attr-defined]

        prompt = build_story_prompt(
            child_name=child_name, age=age, gender=gender,
            condition=condition, hero_characteristics=hero_characteristics,
            preferences=preferences, story_history=story_history,
            story_length=story_length, tone=tone, theme=theme,
            villain_type=villain_type, ending_type=ending_type,
            illustration_style=illustration_style, reading_level=reading_level,
        )

        with AIGenerationTracker('gemini', 'gemini-2.5-flash'):
            gemini_start = time.time()
            model = genai.GenerativeModel('gemini-2.5-flash')  # type: ignore[attr-defined]
            result = model.generate_content(prompt)
            content = result.text.strip()
            gemini_ms = int((time.time() - gemini_start) * 1000)
            usage_counter.record('gemini', success=True)

        # Strip markdown code fences if present
        if content.startswith('```json'):
            content = content[7:]
        elif content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        story_data = json.loads(content)

        # 1b. Content safety: moderate AI output
        all_moderation_flags = []
        for page in story_data.get('pages', []):
            cleaned_text, warnings = moderate_output(page['text'], age)
            page['text'] = sanitize_html(cleaned_text)
            all_moderation_flags.extend(warnings)

            cleaned_prompt, img_warnings = moderate_image_prompt(page.get('imagePrompt', ''))
            page['imagePrompt'] = cleaned_prompt
            all_moderation_flags.extend(img_warnings)

        if all_moderation_flags:
            logger.warning(f'Moderation flags for story: {all_moderation_flags}')

        db.log_api_call('gemini', 'gemini-2.5-flash', True,
                        int((time.time() - start_time) * 1000), user_id=user_id)

        # 2. Generate images with Flux 2 Pro
        flux_key = os.environ.get('FLUX2PRO_API_KEY', '')
        flux_endpoint = os.environ.get('FLUX2PRO_ENDPOINT', '')
        pages_with_images = []
        flux_start = time.time()

        for idx, page in enumerate(story_data['pages']):
            image_url = None
            if flux_key and flux_endpoint and _image_storage:
                try:
                    import base64
                    img_prompt = build_image_prompt(
                        page['imagePrompt'], child_name, age,
                        gender, idx + 1, len(story_data['pages']),
                        illustration_style=illustration_style,
                    )

                    max_retries = 2
                    last_err = None
                    for attempt in range(1, max_retries + 1):
                        try:
                            with AIGenerationTracker('flux2pro', 'flux-2-pro', page_num=idx + 1):
                                gen_resp = requests.post(
                                    flux_endpoint,
                                    headers={
                                        'Authorization': f'Bearer {flux_key}',
                                        'Content-Type': 'application/json',
                                    },
                                    json={
                                        'prompt': img_prompt,
                                        'width': 1024,
                                        'height': 1024,
                                        'n': 1,
                                        'model': 'FLUX.2-pro',
                                    },
                                    timeout=180,
                                )
                                gen_resp.raise_for_status()
                                gen_data = gen_resp.json()

                                b64_str = (gen_data.get('data') or [{}])[0].get('b64_json')
                                if b64_str:
                                    img_bytes = base64.b64decode(b64_str)
                                    img_name = f'story_{int(time.time())}_{idx + 1}.png'
                                    image_url = _image_storage.save_image(img_bytes, img_name)
                                    logger.info(f'Image saved (page {idx + 1}): {img_name}')

                                usage_counter.record('flux2pro', success=bool(image_url))
                                db.log_api_call('flux2pro', 'flux-2-pro', bool(image_url),
                                                user_id=user_id)
                                last_err = None
                                break

                        except Exception as retry_e:
                            last_err = retry_e
                            logger.warning(f'Flux attempt {attempt}/{max_retries} failed: {retry_e}')
                            if attempt < max_retries:
                                time.sleep(2)

                    if last_err:
                        raise last_err

                except Exception as e:
                    logger.error(f'Image generation error page {idx + 1}: {e}')
                    usage_counter.record('flux2pro', success=False)
                    db.log_api_call('flux2pro', 'flux-2-pro', False,
                                    error_message=str(e), user_id=user_id)

            pages_with_images.append({
                'text': page['text'],
                'imageUrl': image_url,
                'pageNumber': idx + 1,
            })

        # 3. Save to DB
        generation_time_ms = int((time.time() - start_time) * 1000)
        flux_ms = int((time.time() - flux_start) * 1000)
        story = db.create_story(
            child_name=child_name, age=age, gender=gender,
            condition=condition, hero_characteristics=hero_characteristics,
            story_title=story_data.get('title', f"{child_name}'s Brave Adventure"),
            pages=pages_with_images, user_id=user_id,
            child_id=child_id, moderation_flags=all_moderation_flags,
            generation_time_ms=generation_time_ms,
        )

        if not story:
            return jsonify({'message': 'Failed to save story'}), 500

        perf_tracker.record_generation(
            story_id=story.get('id', 0),
            gemini_ms=gemini_ms,
            flux_ms=flux_ms,
            total_ms=generation_time_ms,
            pages=len(pages_with_images),
        )

        logger.info(f'Story generated in {generation_time_ms}ms: {story.get("storyTitle")}')
        return jsonify(story), 201

    except json.JSONDecodeError as e:
        logger.error(f'JSON parse error: {e}')
        usage_counter.record('gemini', success=False)
        perf_tracker.record_error('JSONDecodeError')
        return jsonify({'message': 'Failed to parse story from AI response'}), 500
    except Exception as e:
        logger.error(f'Story generation error: {e}', exc_info=True)
        perf_tracker.record_error(type(e).__name__)
        return jsonify({'message': str(e)}), 500


# ── Feedback & Personalization Routes ─────────────────────────────────

@stories_bp.route('/api/stories/<int:story_id>/feedback', methods=['POST'])
@login_required
def submit_feedback(story_id):
    """Record user feedback (rating, favourite page, read time) for a story."""
    data = request.get_json()
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404

    child_id = story.get('child_id')
    if child_id:
        db.record_story_feedback(
            story_id=story_id, child_id=child_id,
            rating=data.get('rating'),
            favorite_page=data.get('favoritePage'),
            read_time_sec=data.get('readTimeSec', 0),
        )
        if data.get('rating') and data['rating'] >= 4:
            theme = story.get('theme', '')
            if theme:
                db.add_preference(child_id, 'theme', theme, weight=data['rating'] / 5.0)

    return jsonify({'success': True})


@stories_bp.route('/api/stories/<int:story_id>/user-feedback', methods=['POST'])
@login_required
def submit_user_feedback(story_id):
    """Submit user feedback: star rating, emoji reaction, helpful flag, comment."""
    data = request.get_json()
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404

    user_id = g.user_id

    star_rating = data.get('starRating')
    if star_rating is not None:
        star_rating = int(star_rating)
        if star_rating < 1 or star_rating > 5:
            return jsonify({'message': 'Star rating must be 1-5'}), 400

    emoji = data.get('emojiReaction')
    if emoji and emoji not in ('\U0001f60a', '\U0001f610', '\U0001f622'):
        return jsonify({'message': 'Invalid emoji reaction'}), 400

    is_helpful = data.get('isHelpful')
    comment = (data.get('comment') or '').strip()
    if comment:
        comment = sanitize_html(comment[:500])

    page_number = data.get('pageNumber')

    result = db.submit_user_feedback(
        story_id=story_id, user_id=user_id,
        star_rating=star_rating, emoji_reaction=emoji,
        is_helpful=is_helpful, comment=comment,
        page_number=page_number,
    )
    return jsonify({'success': True, 'feedback': result}), 201


@stories_bp.route('/api/stories/<int:story_id>/user-feedback', methods=['GET'])
@login_required
def get_story_feedback(story_id):
    """Get aggregated feedback summary for a story (only if owned by authenticated user)."""
    story = db.get_story(story_id, user_id=g.user_id)
    if not story:
        return jsonify({'message': 'Story not found'}), 404
    return jsonify(db.get_story_feedback_summary(story_id))


@stories_bp.route('/api/admin/feedback', methods=['GET'])
@login_required
def admin_feedback_stats():
    """Get admin feedback statistics."""
    return jsonify(db.get_admin_feedback_stats())


@stories_bp.route('/api/feedback/overall', methods=['POST'])
@login_required
def submit_overall_feedback():
    """Submit overall platform feedback (not tied to a specific story)."""
    data = request.get_json() or {}
    user_id = getattr(g, 'user_id', None)

    star_rating = data.get('starRating')
    if star_rating is not None:
        star_rating = int(star_rating)
        if star_rating < 1 or star_rating > 5:
            return jsonify({'message': 'Star rating must be 1-5'}), 400

    emoji = data.get('emojiReaction')
    if emoji and emoji not in ('\U0001f60a', '\U0001f610', '\U0001f622'):
        return jsonify({'message': 'Invalid emoji reaction'}), 400

    is_helpful = data.get('isHelpful')
    comment = (data.get('comment') or '').strip()
    if comment:
        comment = sanitize_html(comment[:500])

    result = db.submit_user_feedback(
        story_id=0, user_id=user_id,
        star_rating=star_rating, emoji_reaction=emoji,
        is_helpful=is_helpful, comment=comment,
        page_number=None,
    )
    return jsonify({'success': True, 'feedback': result}), 201


@stories_bp.route('/api/children/<int:child_id>/preferences', methods=['GET'])
@login_required
def get_preferences(child_id):
    """Return learned personalisation preferences for a child (only if owned by authenticated user)."""
    if not db.verify_child_owner(child_id, g.user_id):
        return jsonify({'message': 'Child not found'}), 404
    return jsonify(db.get_preferences(child_id))
