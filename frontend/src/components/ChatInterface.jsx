import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import AttachmentPanel from './AttachmentPanel';
import ContextStatus from './ContextStatus';
import { MODES, findMode } from '../modes';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  activeMode,
  onChangeMode,
  deepCheck,
  onChangeDeepCheck,
  subMode,
  onChangeSubMode,
  onVerdictDecided,
}) {
  const [input, setInput] = useState('');
  const [attachment, setAttachment] = useState('');
  const [previousFindings, setPreviousFindings] = useState('');
  const messagesEndRef = useRef(null);

  const isSpecVerify = activeMode === 'spec_verify';
  const isFixVerification = isSpecVerify && subMode === 'fix_verification';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(
        input,
        attachment.trim() ? attachment : null,
        isFixVerification && previousFindings.trim() ? previousFindings : null,
      );
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleModeChange = (e) => {
    const raw = e.target.value;
    const next = raw === '' ? null : raw;
    onChangeMode?.(next);
  };

  const activeModeDef = findMode(activeMode);

  const modeBar = (
    <div className="mode-bar">
      <label className="mode-bar-label" htmlFor="mode-select">
        Mode
      </label>
      <select
        id="mode-select"
        className="mode-select"
        value={activeMode == null ? '' : activeMode}
        onChange={handleModeChange}
        disabled={isLoading}
      >
        {MODES.map((m) => (
          <option key={m.key ?? 'free'} value={m.key == null ? '' : m.key}>
            {m.label}
          </option>
        ))}
      </select>
      <div className="mode-bar-description">{activeModeDef.description}</div>
      {isSpecVerify && activeModeDef.subModes && (
        <div className="submode-toggle" role="group" aria-label="Spec Verify sub-mode">
          {activeModeDef.subModes.map((sm) => (
            <button
              key={sm.key}
              type="button"
              className={`submode-button ${subMode === sm.key ? 'is-active' : ''}`}
              onClick={() => onChangeSubMode?.(sm.key)}
              disabled={isLoading}
            >
              {sm.label}
            </button>
          ))}
        </div>
      )}
      <label
        className={`challenge-toggle ${deepCheck ? 'is-on' : ''}`}
        title="When ON, every model output at every stage is fed back to itself with a stage-aware challenge prompt before moving on. Roughly 2× latency and 2× API spend, but pushes past first-pass surface-level answers."
      >
        <input
          type="checkbox"
          checked={!!deepCheck}
          onChange={(e) => onChangeDeepCheck?.(e.target.checked)}
          disabled={isLoading}
        />
        <span className="challenge-toggle-text">
          Challenge Mode
          <span className="challenge-toggle-state">{deepCheck ? 'ON' : 'OFF'}</span>
        </span>
      </label>
      <ContextStatus />
    </div>
  );

  const previousFindingsPanel = isFixVerification ? (
    <div className="previous-findings-panel">
      <div className="previous-findings-header">
        <span className="previous-findings-label">Previous Findings</span>
        <span className="previous-findings-hint">
          Paste the prior verdict / findings list. Each model verifies these
          against the updated spec — it does not re-review the whole spec.
        </span>
      </div>
      <textarea
        className="previous-findings-textarea"
        placeholder="Paste the consolidated issue list from the previous Cross-Reference Review pass…"
        value={previousFindings}
        onChange={(e) => setPreviousFindings(e.target.value)}
        disabled={isLoading}
        rows={6}
      />
    </div>
  ) : null;

  if (!conversation) {
    return (
      <div className="chat-interface">
        {modeBar}
        <AttachmentPanel value={attachment} onChange={setAttachment} disabled={isLoading} />
        {previousFindingsPanel}
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      {modeBar}
      <AttachmentPanel value={attachment} onChange={setAttachment} disabled={isLoading} />
      {previousFindingsPanel}
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">
                    You
                    {msg.mode && (
                      <span className="message-mode-pill">{findMode(msg.mode).short}</span>
                    )}
                  </div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">
                    LLM Council
                    {msg.metadata?.mode && (
                      <span className="message-mode-pill">
                        {findMode(msg.metadata.mode).short}
                      </span>
                    )}
                  </div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>
                        {msg.metadata?.flow === 'debate'
                          ? 'Running Round 1: opening arguments...'
                          : 'Running Stage 1: Collecting individual responses...'}
                      </span>
                    </div>
                  )}
                  {msg.stage1 && (
                    <Stage1
                      responses={msg.stage1}
                      flow={msg.metadata?.flow}
                    />
                  )}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>
                        {msg.metadata?.flow === 'debate'
                          ? 'Running Round 2: rebuttals...'
                          : 'Running Stage 2: Peer rankings...'}
                      </span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                      flow={msg.metadata?.flow}
                    />
                  )}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>
                        {msg.metadata?.flow === 'debate'
                          ? 'Chairman: rendering the verdict...'
                          : 'Running Stage 3: Final synthesis...'}
                      </span>
                    </div>
                  )}
                  {msg.stage3 && (
                    <Stage3
                      finalResponse={msg.stage3}
                      flow={msg.metadata?.flow}
                      message={msg}
                      onVerdictDecided={onVerdictDecided}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form className="input-form" onSubmit={handleSubmit}>
          <textarea
            className="message-input"
            placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || isLoading}
          >
            Send
          </button>
        </form>
      )}
    </div>
  );
}
