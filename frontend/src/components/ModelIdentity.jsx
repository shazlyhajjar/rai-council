import { identityFor, chairmanIdentity } from '../modelIdentity';
import './ModelIdentity.css';

/**
 * Renders the persistent display identity (name + subtitle + model caption)
 * for a council member or the chairman.
 *
 * Props:
 *   model         — OpenRouter id string
 *   chairman      — boolean, picks the chairman identity instead
 *   size          — "card" (default, big) | "tab" (compact, inline)
 *   showModel     — show the raw model id underneath (default true for card, false for tab)
 *   trailing      — optional ReactNode rendered to the right of the name (badges, etc.)
 */
export default function ModelIdentity({
  model,
  chairman = false,
  size = 'card',
  showModel,
  trailing,
}) {
  const id = chairman ? chairmanIdentity(model) : identityFor(model);
  const renderModel = showModel ?? size === 'card';

  return (
    <div className={`model-identity size-${size}`} style={{ '--identity-color': id.color }}>
      <div className="model-identity-line">
        <span className="model-identity-name">{id.name}</span>
        {trailing && <span className="model-identity-trailing">{trailing}</span>}
      </div>
      {id.subtitle && size !== 'tab-name-only' && (
        <span className="model-identity-subtitle">{id.subtitle}</span>
      )}
      {renderModel && model && (
        <span className="model-identity-model">powered by {model}</span>
      )}
    </div>
  );
}

/**
 * Compact name + subtitle for tab buttons. Returns a fragment, not a styled
 * card — fits inside an existing <button>.
 */
export function TabIdentity({ model, trailing }) {
  const id = identityFor(model);
  return (
    <span className="tab-identity" style={{ '--identity-color': id.color }}>
      <span className="tab-identity-name">{id.name}</span>
      <span className="tab-identity-subtitle">{id.subtitle}</span>
      {trailing && <span className="tab-identity-trailing">{trailing}</span>}
    </span>
  );
}
