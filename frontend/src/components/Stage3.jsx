import ReactMarkdown from 'react-markdown';
import CopyButton from './CopyButton';
import ChairmanDecision from './ChairmanDecision';
import ModelIdentity from './ModelIdentity';
import { flattenAssistantMessage } from '../flattenMessage';
import './Stage3.css';

export default function Stage3({ finalResponse, flow, message, onVerdictDecided }) {
  if (!finalResponse) {
    return null;
  }

  const title = flow === 'debate' ? 'Chairman Verdict' : 'Stage 3: Final Council Answer';
  const verdictId = message?.verdict_id;
  const verdict = message?.verdict;

  return (
    <div className="stage stage3">
      <div className="stage3-header">
        <h3 className="stage-title">{title}</h3>
        <div className="stage3-actions">
          {message && (
            <CopyButton
              variant="labeled"
              label="Copy All"
              getText={() => flattenAssistantMessage(message)}
              title="Copy the full council output (all stages) as markdown"
            />
          )}
        </div>
      </div>
      <div className="final-response with-copy-button">
        <CopyButton
          getText={() => finalResponse.response || ''}
          title="Copy chairman synthesis"
        />
        <ModelIdentity model={finalResponse.model} chairman size="card" />
        <div className="final-text markdown-content">
          <ReactMarkdown>{finalResponse.response}</ReactMarkdown>
        </div>
      </div>
      <ChairmanDecision
        verdictId={verdictId}
        verdict={verdict}
        onDecided={(updated) => onVerdictDecided?.(updated)}
      />
    </div>
  );
}
