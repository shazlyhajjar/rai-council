import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import HistoryPage from './components/HistoryPage';
import TopNav from './components/TopNav';
import { api } from './api';
import { DEFAULT_MODE_KEY, DEFAULT_SUB_MODE } from './modes';
import './App.css';

const DEEP_CHECK_KEY = 'rai-council:deep-check';

function readDeepCheckPref() {
  try {
    const stored = localStorage.getItem(DEEP_CHECK_KEY);
    // Default ON (per spec); only "false" turns it off.
    return stored === null ? true : stored !== 'false';
  } catch {
    return true;
  }
}

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [activeMode, setActiveMode] = useState(DEFAULT_MODE_KEY);
  const [activeView, setActiveView] = useState('chat'); // 'chat' | 'history'
  const [deepCheck, setDeepCheck] = useState(readDeepCheckPref);
  // spec_verify sub-mode. Session-level (mirrors activeMode — not persisted).
  const [subMode, setSubMode] = useState(DEFAULT_SUB_MODE);

  // Persist Challenge Mode preference across sessions.
  useEffect(() => {
    try {
      localStorage.setItem(DEEP_CHECK_KEY, String(deepCheck));
    } catch {
      /* localStorage unavailable — ignore */
    }
  }, [deepCheck]);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, message_count: 0 },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
  };

  const handleVerdictDecided = (updated) => {
    setCurrentConversation((prev) => {
      if (!prev) return prev;
      const messages = prev.messages.map((msg) => {
        if (msg.verdict_id === updated.id) {
          return {
            ...msg,
            verdict: {
              id: updated.id,
              decision: updated.decision,
              override_reasoning: updated.override_reasoning,
              decided_at: updated.decided_at,
              created_at: updated.created_at,
            },
          };
        }
        return msg;
      });
      return { ...prev, messages };
    });
  };

  const handleSendMessage = async (content, attachment = null, previousFindings = null) => {
    if (!currentConversationId) return;

    const modeForThisMessage = activeMode;
    const deepCheckForThisMessage = deepCheck;
    const subModeForThisMessage = modeForThisMessage === 'spec_verify' ? subMode : null;
    const previousFindingsForThisMessage =
      modeForThisMessage === 'spec_verify' && subMode === 'fix_verification'
        ? previousFindings
        : null;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI (with mode + attachment for display).
      const userMessage = {
        role: 'user',
        content,
        mode: modeForThisMessage,
        ...(attachment ? { attachment } : {}),
      };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: { mode: modeForThisMessage },
        loading: {
          stage1: false,
          stage2: false,
          stage3: false,
        },
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      await api.sendMessageStream(currentConversationId, content, modeForThisMessage, attachment, deepCheckForThisMessage, (eventType, event) => {
        switch (eventType) {
          case 'mode_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.metadata = {
                ...(lastMsg.metadata || {}),
                mode: event.mode,
                flow: event.flow,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage1_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage1 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage1_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage1 = event.data;
              if (event.metadata) {
                lastMsg.metadata = { ...(lastMsg.metadata || {}), ...event.metadata };
              }
              lastMsg.loading.stage1 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage2_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage2 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage2_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage2 = event.data;
              if (event.metadata) {
                lastMsg.metadata = { ...(lastMsg.metadata || {}), ...event.metadata };
              }
              lastMsg.loading.stage2 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage3_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage3 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage3_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = event.data;
              lastMsg.loading.stage3 = false;
              return { ...prev, messages };
            });
            break;

          case 'verdict_created':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.verdict_id = event.verdict_id;
              lastMsg.verdict = { id: event.verdict_id, decision: null };
              return { ...prev, messages };
            });
            break;

          case 'title_complete':
            // Reload conversations to get updated title
            loadConversations();
            break;

          case 'complete':
            // Stream complete, reload conversations list
            loadConversations();
            setIsLoading(false);
            break;

          case 'error':
            console.error('Stream error:', event.message);
            setIsLoading(false);
            break;

          default:
            console.log('Unknown event type:', eventType);
        }
      }, {
        subMode: subModeForThisMessage,
        previousFindings: previousFindingsForThisMessage,
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <TopNav activeView={activeView} onChangeView={setActiveView} />
      <div className="app-body">
        {activeView === 'chat' ? (
          <>
            <Sidebar
              conversations={conversations}
              currentConversationId={currentConversationId}
              onSelectConversation={handleSelectConversation}
              onNewConversation={handleNewConversation}
            />
            <ChatInterface
              conversation={currentConversation}
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
              activeMode={activeMode}
              onChangeMode={setActiveMode}
              deepCheck={deepCheck}
              onChangeDeepCheck={setDeepCheck}
              subMode={subMode}
              onChangeSubMode={setSubMode}
              onVerdictDecided={handleVerdictDecided}
            />
          </>
        ) : (
          <HistoryPage />
        )}
      </div>
    </div>
  );
}

export default App;
