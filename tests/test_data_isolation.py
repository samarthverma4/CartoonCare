"""
Tests for user data isolation: ensures users cannot access each other's
stories, children, or feedback.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import database_v2 as db


# ── Helpers ───────────────────────────────────────────────────────────

def _register(client, email, name='User'):
    """Register a user and return the Authorization header."""
    resp = client.post('/api/auth/register', json={
        'email': email,
        'name': name,
        'password': 'securepassword123',
    })
    assert resp.status_code == 201
    token = resp.get_json()['token']
    return {'Authorization': f'Bearer {token}'}


def _create_child(client, headers, name='Child', age=6):
    """Create a child profile for the authenticated user."""
    resp = client.post('/api/children', json={
        'name': name,
        'age': age,
        'gender': 'neutral',
        'conditions': ['ADHD'],
    }, headers=headers)
    assert resp.status_code == 201
    return resp.get_json()


def _create_story(client, headers, child_name='Kid'):
    """Insert a story directly via DB for the user (bypasses AI generation)."""
    # Decode user_id from the token
    from auth import decode_token
    token = headers['Authorization'].split(' ')[1]
    payload = decode_token(token)
    assert payload is not None, 'Invalid token'
    user_id = payload['user_id']

    story = db.create_story(
        child_name=child_name, age=6, gender='neutral',
        condition='ADHD', hero_characteristics='brave',
        story_title=f"{child_name}'s Adventure",
        pages=[{'text': 'Once upon a time...', 'imageUrl': None, 'pageNumber': 1}],
        user_id=user_id,
    )
    assert story is not None, 'Failed to create story'
    return story


# ── Story Isolation Tests ────────────────────────────────────────────

class TestStoryIsolation:
    """Ensure users can only see/modify their own stories."""

    def test_list_stories_only_own(self, client):
        """User A cannot see User B's stories in the list endpoint."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        _create_story(client, hdr_a, 'AliceKid')
        _create_story(client, hdr_b, 'BobKid')

        # Alice should see only her story
        resp = client.get('/api/stories', headers=hdr_a)
        assert resp.status_code == 200
        stories = resp.get_json()
        assert len(stories) == 1
        assert stories[0]['childName'] == 'AliceKid'

        # Bob should see only his story
        resp = client.get('/api/stories', headers=hdr_b)
        assert resp.status_code == 200
        stories = resp.get_json()
        assert len(stories) == 1
        assert stories[0]['childName'] == 'BobKid'

    def test_get_story_forbidden_for_other_user(self, client):
        """User A cannot fetch User B's story by ID."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        story_b = _create_story(client, hdr_b, 'BobKid')
        story_id = story_b['id']

        # Alice tries to read Bob's story → 404
        resp = client.get(f'/api/stories/{story_id}', headers=hdr_a)
        assert resp.status_code == 404

    def test_delete_story_forbidden_for_other_user(self, client):
        """User A cannot delete User B's story."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        story_b = _create_story(client, hdr_b, 'BobKid')
        story_id = story_b['id']

        # Alice tries to delete Bob's story → 404 (not found for her)
        resp = client.delete(f'/api/stories/{story_id}', headers=hdr_a)
        assert resp.status_code == 404

        # Verify story still exists for Bob
        resp = client.get(f'/api/stories/{story_id}', headers=hdr_b)
        assert resp.status_code == 200

    def test_toggle_favorite_forbidden_for_other_user(self, client):
        """User A cannot toggle favorite on User B's story."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        story_b = _create_story(client, hdr_b, 'BobKid')
        story_id = story_b['id']

        resp = client.post(f'/api/stories/{story_id}/favorite', headers=hdr_a)
        assert resp.status_code == 404

    def test_favorites_list_only_own(self, client):
        """User A's favorites list doesn't include User B's favorited stories."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        story_b = _create_story(client, hdr_b, 'BobKid')
        # Bob favorites his story
        client.post(f'/api/stories/{story_b["id"]}/favorite', headers=hdr_b)

        # Alice should see no favorites
        resp = client.get('/api/stories/favorites', headers=hdr_a)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_unauthenticated_cannot_list_stories(self, client):
        """Unauthenticated request to stories list returns 401."""
        resp = client.get('/api/stories')
        assert resp.status_code == 401

    def test_unauthenticated_cannot_delete_story(self, client):
        """Unauthenticated request to delete a story returns 401."""
        resp = client.delete('/api/stories/1')
        assert resp.status_code == 401


# ── Children Isolation Tests ─────────────────────────────────────────

class TestChildIsolation:
    """Ensure users can only see/modify their own child profiles."""

    def test_list_children_only_own(self, client):
        """User A cannot see User B's children in the list endpoint."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        _create_child(client, hdr_a, name='AliceChild')
        _create_child(client, hdr_b, name='BobChild')

        resp = client.get('/api/children', headers=hdr_a)
        assert resp.status_code == 200
        children = resp.get_json()
        assert len(children) == 1
        assert children[0]['name'] == 'AliceChild'

    def test_update_child_forbidden_for_other_user(self, client):
        """User A cannot update User B's child profile."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        child_b = _create_child(client, hdr_b, name='BobChild')
        child_id = child_b['id']

        resp = client.put(f'/api/children/{child_id}', json={
            'name': 'Hacked',
        }, headers=hdr_a)
        assert resp.status_code == 404

        # Verify name unchanged for Bob
        resp = client.get('/api/children', headers=hdr_b)
        assert resp.get_json()[0]['name'] == 'BobChild'

    def test_delete_child_forbidden_for_other_user(self, client):
        """User A cannot delete User B's child profile."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        child_b = _create_child(client, hdr_b, name='BobChild')
        child_id = child_b['id']

        resp = client.delete(f'/api/children/{child_id}', headers=hdr_a)
        assert resp.status_code == 404

        # Verify child still exists for Bob
        resp = client.get('/api/children', headers=hdr_b)
        assert len(resp.get_json()) == 1

    def test_get_preferences_forbidden_for_other_user(self, client):
        """User A cannot read User B's child preferences."""
        hdr_a = _register(client, 'alice@test.com', 'Alice')
        hdr_b = _register(client, 'bob@test.com', 'Bob')

        child_b = _create_child(client, hdr_b, name='BobChild')
        child_id = child_b['id']

        resp = client.get(f'/api/children/{child_id}/preferences', headers=hdr_a)
        assert resp.status_code == 404

    def test_unauthenticated_cannot_list_children(self, client):
        """Unauthenticated request to children list returns 401."""
        resp = client.get('/api/children')
        assert resp.status_code == 401
