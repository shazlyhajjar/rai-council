import BalanceIndicator from './BalanceIndicator';
import './TopNav.css';

const VIEWS = [
  { key: 'chat', label: 'Chat' },
  { key: 'history', label: 'History' },
];

export default function TopNav({ activeView, onChangeView }) {
  return (
    <nav className="top-nav">
      <div className="top-nav-brand">LLM Council</div>
      <div className="top-nav-tabs">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            className={`top-nav-tab ${activeView === v.key ? 'active' : ''}`}
            onClick={() => onChangeView(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <BalanceIndicator />
    </nav>
  );
}
