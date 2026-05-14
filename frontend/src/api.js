/**
 * API client for the LLM Council backend.
 *
 * Dev (vite serve) → talks to FastAPI on a separate port.
 * Prod (vite build) → same-origin; FastAPI serves the bundled frontend AND
 *   the API, so an empty base means "use the current origin".
 */

const API_BASE = import.meta.env.PROD ? '' : 'http://localhost:8001';

export const api = {
  /**
   * Fetch OpenRouter credit balance + month-to-date usage. Cached 60s server-side.
   */
  async getOpenRouterBalance() {
    const response = await fetch(`${API_BASE}/api/balance/openrouter`);
    if (!response.ok) throw new Error('Failed to load OpenRouter balance');
    return response.json();
  },

  /**
   * Fetch OpenAI month-to-date spend (no balance endpoint exists at OpenAI;
   * remaining is computed against OPENAI_MONTHLY_CAP if set).
   */
  async getOpenAIBalance() {
    const response = await fetch(`${API_BASE}/api/balance/openai`);
    if (!response.ok) throw new Error('Failed to load OpenAI balance');
    return response.json();
  },

  /**
   * Fetch the RAI Council Brief content + metadata.
   * Returns { loaded, path, chars, words, lines, updated_at, content }.
   */
  async getContext() {
    const response = await fetch(`${API_BASE}/api/context`);
    if (!response.ok) {
      throw new Error('Failed to load council context');
    }
    return response.json();
  },

  /**
   * Replace the RAI Council Brief on disk.
   * Returns the same shape as getContext().
   */
  async setContext(content) {
    const response = await fetch(`${API_BASE}/api/context`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      throw new Error('Failed to save council context');
    }
    return response.json();
  },

  /**
   * List verdicts, newest first. Optional filters: mode, decision (accept|override|undecided).
   */
  async listVerdicts({ mode, decision, limit = 200 } = {}) {
    const params = new URLSearchParams();
    if (mode) params.set('mode', mode);
    if (decision) params.set('decision', decision);
    if (limit) params.set('limit', String(limit));
    const qs = params.toString();
    const response = await fetch(`${API_BASE}/api/verdicts${qs ? `?${qs}` : ''}`);
    if (!response.ok) throw new Error('Failed to list verdicts');
    return response.json();
  },

  async getVerdict(verdictId) {
    const response = await fetch(`${API_BASE}/api/verdicts/${verdictId}`);
    if (!response.ok) throw new Error('Failed to load verdict');
    return response.json();
  },

  /**
   * Mark a verdict as accepted or overridden. `reasoning` is only used for overrides.
   */
  async decideVerdict(verdictId, decision, reasoning = null) {
    const response = await fetch(`${API_BASE}/api/verdicts/${verdictId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, reasoning }),
    });
    if (!response.ok) throw new Error('Failed to save decision');
    return response.json();
  },


  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {string|null} mode - Operating mode key, or null for free chat
   * @param {string|null} attachment - Optional text/markdown context
   */
  async sendMessage(conversationId, content, mode = null, attachment = null) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content, mode, attachment }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {string|null} mode - Operating mode key, or null for free chat
   * @param {string|null} attachment - Optional text/markdown context
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @returns {Promise<void>}
   */
  async sendMessageStream(conversationId, content, mode, attachment, onEvent) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content, mode, attachment }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          try {
            const event = JSON.parse(data);
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }
  },
};
