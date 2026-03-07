/* ─── Help & Support / Feedback Page ──────────────────── */

const Auth = {
  getToken()  { return localStorage.getItem('cc_token'); },
  getUser()   { try { return JSON.parse(localStorage.getItem('cc_user')); } catch { return null; } },
  isLoggedIn(){ return !!this.getToken(); },
  headers()   {
    const h = { 'Content-Type': 'application/json' };
    const t = this.getToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  },
};

function showToast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

// ── Init ───────────────────────────────────────────────
(function init() {
  if (!Auth.isLoggedIn()) {
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('login-required').style.display = '';
    return;
  }
  setupOverallFeedback();
  loadStories();
})();

// ── Overall Experience Feedback ────────────────────────
let overallData = { starRating: null, emojiReaction: null, isHelpful: null };

function setupOverallFeedback() {
  // Stars
  document.querySelectorAll('#overall-stars .star-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      overallData.starRating = parseInt(btn.dataset.val);
      document.querySelectorAll('#overall-stars .star-btn').forEach((s, i) => {
        s.classList.toggle('active', i < overallData.starRating);
      });
    });
  });

  // Emoji
  document.querySelectorAll('#overall-emoji .emoji-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      overallData.emojiReaction = btn.dataset.emoji;
      document.querySelectorAll('#overall-emoji .emoji-btn').forEach(e => e.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Helpful
  document.querySelectorAll('#overall-helpful .helpful-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      overallData.isHelpful = btn.dataset.val === 'yes';
      document.querySelectorAll('#overall-helpful .helpful-btn').forEach(h => h.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Submit
  document.getElementById('overall-submit').addEventListener('click', async () => {
    if (!overallData.starRating) {
      showToast('Please select a star rating', 'error');
      return;
    }
    const comment = (document.getElementById('overall-comment').value || '').trim();
    try {
      const res = await fetch('/api/feedback/overall', {
        method: 'POST',
        headers: Auth.headers(),
        body: JSON.stringify({
          starRating: overallData.starRating,
          emojiReaction: overallData.emojiReaction,
          isHelpful: overallData.isHelpful,
          comment: comment,
        }),
      });
      if (res.ok) {
        showToast('Thanks for your feedback!');
        // Reset form
        overallData = { starRating: null, emojiReaction: null, isHelpful: null };
        document.querySelectorAll('#overall-stars .star-btn').forEach(s => s.classList.remove('active'));
        document.querySelectorAll('#overall-emoji .emoji-btn').forEach(e => e.classList.remove('active'));
        document.querySelectorAll('#overall-helpful .helpful-btn').forEach(h => h.classList.remove('active'));
        document.getElementById('overall-comment').value = '';
      } else {
        const data = await res.json();
        showToast(data.message || 'Failed to submit', 'error');
      }
    } catch {
      showToast('Failed to submit feedback', 'error');
    }
  });
}

// ── Story List ─────────────────────────────────────────
let selectedStoryId = null;
let storyFeedbackData = { starRating: null, emojiReaction: null, isHelpful: null };

async function loadStories() {
  const el = document.getElementById('stories-list');
  try {
    const res = await fetch('/api/stories', { headers: Auth.headers() });
    if (!res.ok) throw new Error('Failed');
    const data = await res.json();
    const stories = data.stories || data || [];

    if (!stories.length) {
      el.innerHTML = '<div class="empty-state"><p>No stories yet</p><p class="hint">Create a story first, then come back to rate it!</p><a href="/create" class="btn btn-primary btn-sm" style="margin-top:1rem">Create Story</a></div>';
      return;
    }

    el.innerHTML = stories.map(s => {
      const date = s.created_at ? new Date(s.created_at).toLocaleDateString() : '';
      return `
        <div class="story-feedback-card" data-story-id="${s.id}" style="
          display:flex;align-items:center;gap:1rem;padding:1rem 1.25rem;
          border:2px solid rgba(124,58,237,.08);border-radius:var(--radius);
          margin-bottom:.75rem;cursor:pointer;transition:all .2s;background:var(--card)
        ">
          <div style="
            width:3rem;height:3rem;border-radius:.875rem;
            background:linear-gradient(135deg,#7c3aed,#a78bfa);
            color:#fff;display:flex;align-items:center;justify-content:center;
            font-size:1.25rem;flex-shrink:0
          ">📖</div>
          <div style="flex:1;min-width:0">
            <div style="font-weight:700;color:var(--foreground);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              ${escHtml(s.story_title || s.title || 'Untitled Story')}
            </div>
            <div style="font-size:.8rem;color:var(--muted-fg);display:flex;gap:1rem;margin-top:.15rem">
              <span>${escHtml(s.condition || '')}</span>
              <span>${date}</span>
            </div>
          </div>
          <div style="font-size:.8rem;font-weight:700;color:var(--primary);white-space:nowrap">
            Rate →
          </div>
        </div>`;
    }).join('');

    // Click handler
    el.querySelectorAll('.story-feedback-card').forEach(card => {
      card.addEventListener('mouseenter', () => {
        card.style.borderColor = 'rgba(124,58,237,.25)';
        card.style.boxShadow = '0 4px 16px rgba(0,0,0,.08)';
      });
      card.addEventListener('mouseleave', () => {
        card.style.borderColor = 'rgba(124,58,237,.08)';
        card.style.boxShadow = 'none';
      });
      card.addEventListener('click', () => {
        const sid = parseInt(card.dataset.storyId);
        const title = card.querySelector('div[style*="font-weight:700"]').textContent.trim();
        openStoryFeedback(sid, title);
      });
    });

  } catch (e) {
    console.error('Failed to load stories:', e);
    el.innerHTML = '<div class="empty-state"><p>Failed to load stories</p></div>';
  }
}

function openStoryFeedback(storyId, title) {
  selectedStoryId = storyId;
  storyFeedbackData = { starRating: null, emojiReaction: null, isHelpful: null };

  document.getElementById('story-feedback-title').textContent = 'Rate: ' + title;
  document.getElementById('story-feedback-desc').textContent = 'Share your thoughts on this story';

  // Reset
  document.querySelectorAll('#story-stars .star-btn').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('#story-emoji .emoji-btn').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('#story-helpful .helpful-btn').forEach(h => h.classList.remove('active'));
  document.getElementById('story-comment').value = '';

  const section = document.getElementById('story-feedback-section');
  section.style.display = '';
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Setup story feedback form interactions
(function setupStoryFeedback() {
  document.querySelectorAll('#story-stars .star-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      storyFeedbackData.starRating = parseInt(btn.dataset.val);
      document.querySelectorAll('#story-stars .star-btn').forEach((s, i) => {
        s.classList.toggle('active', i < storyFeedbackData.starRating);
      });
    });
  });

  document.querySelectorAll('#story-emoji .emoji-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      storyFeedbackData.emojiReaction = btn.dataset.emoji;
      document.querySelectorAll('#story-emoji .emoji-btn').forEach(e => e.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  document.querySelectorAll('#story-helpful .helpful-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      storyFeedbackData.isHelpful = btn.dataset.val === 'yes';
      document.querySelectorAll('#story-helpful .helpful-btn').forEach(h => h.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  document.getElementById('story-submit').addEventListener('click', async () => {
    if (!selectedStoryId || !storyFeedbackData.starRating) {
      showToast('Please select a star rating', 'error');
      return;
    }
    const comment = (document.getElementById('story-comment').value || '').trim();
    try {
      const res = await fetch('/api/stories/' + selectedStoryId + '/user-feedback', {
        method: 'POST',
        headers: Auth.headers(),
        body: JSON.stringify({
          starRating: storyFeedbackData.starRating,
          emojiReaction: storyFeedbackData.emojiReaction,
          isHelpful: storyFeedbackData.isHelpful,
          comment: comment,
        }),
      });
      if (res.ok || res.status === 201) {
        showToast('Thanks for rating this story!');
        document.getElementById('story-feedback-section').style.display = 'none';
        selectedStoryId = null;
      } else {
        const data = await res.json();
        showToast(data.message || 'Failed to submit', 'error');
      }
    } catch {
      showToast('Failed to submit feedback', 'error');
    }
  });

  document.getElementById('story-cancel').addEventListener('click', () => {
    document.getElementById('story-feedback-section').style.display = 'none';
    selectedStoryId = null;
  });
})();
