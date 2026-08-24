import React from 'react';

export interface RangeIndicatorProps {
  value: string;
  // Nullable: the backend sends null for a one-sided bound (e.g. "<150") and
  // for any result it declined to evaluate.
  ref_min?: number | null;
  ref_max?: number | null;
  status: 'HIGH' | 'LOW' | 'NORMAL' | 'UNKNOWN';
  unit: string;
  /** Backend-rendered range, e.g. "<150 mg/dL" or ">40 mg/dL". */
  reference_text?: string | null;
  /** 'report' when the range was read off the patient's own report. */
  reference_source?: 'table' | 'report' | null;
}

export const RangeIndicator: React.FC<RangeIndicatorProps> = ({
  value,
  ref_min,
  ref_max,
  status,
  unit,
  reference_text,
  reference_source
}) => {
  const numericValue = parseFloat(value);

  // A result we declined to check must not display a reference range, even
  // though the backend still fills those fields in for diagnostics. Showing
  // "NOT CHECKED" beside "Normal: <5" reads as a contradiction - it happened
  // for Cholesterol Ratio, where the report's mg/dL is meaningless for a ratio.
  const checked = status !== 'UNKNOWN';
  const hasRange = checked && ref_min != null && ref_max != null && !isNaN(numericValue);

  // A one-sided bound ("<150", ">40") is a real reference range, but it has no
  // opposite end to draw a bar between. 54 of the 333 evaluable rows are this
  // shape - Triglycerides, LDL, HDL, PSA, CRP, Troponin - and every one of them
  // used to render as "reference range unavailable" while still showing a
  // computed status, which reads like a contradiction.
  const oneSided = checked && !hasRange && (ref_min != null || ref_max != null);
  if (oneSided) {
    const label = reference_text
      || (ref_max != null ? `under ${ref_max} ${unit}` : `over ${ref_min} ${unit}`);
    const ok = status === 'NORMAL';
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
        <div style={{ height: '6px', borderRadius: '3px', width: '100%', display: 'flex', overflow: 'hidden' }}>
          <div style={{
            flex: 1,
            backgroundColor: ok ? 'rgba(60, 157, 110, 0.35)' : 'var(--color-border)'
          }} />
          <div style={{
            flex: 1,
            backgroundColor: ok ? 'var(--color-border)'
              : (status === 'HIGH' ? 'var(--color-status-high)' : 'var(--color-status-low)')
          }} />
        </div>
        <span className="caption" style={{ fontSize: '11px', textAlign: 'left' }}>
          Normal: {label}
          {reference_source === 'report' && ' (from your report)'}
        </span>
      </div>
    );
  }

  if (!hasRange) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
        <div style={{ height: '6px', backgroundColor: 'var(--color-status-unknown-bg)', borderRadius: '3px', width: '100%' }} />
        <span className="caption" style={{ fontSize: '11px', textAlign: 'left' }}>not checked against a reference range</span>
      </div>
    );
  }

  // Calculate dot percentage position
  // Left 25% is Low, Middle 50% is Normal, Right 25% is High
  let positionPercent = 50;

  const min = ref_min!;
  const max = ref_max!;

  if (status === 'NORMAL') {
    // Map normal range linearly between 25% and 75%
    const range = max - min;
    const offset = range > 0 ? (numericValue - min) / range : 0.5;
    positionPercent = 25 + offset * 50;
  } else if (status === 'LOW') {
    // Map below normal between 5% and 25%
    const offset = min > 0 ? numericValue / min : 0.5;
    positionPercent = Math.max(5, offset * 25);
  } else if (status === 'HIGH') {
    // Map above normal between 75% and 95%
    const excess = numericValue - max;
    const offset = max > 0 ? excess / max : 0.5;
    positionPercent = Math.min(95, 75 + offset * 20);
  }

  // Determine dot color
  let dotColor = 'var(--color-status-normal)';
  if (status === 'HIGH') dotColor = 'var(--color-status-high)';
  if (status === 'LOW') dotColor = 'var(--color-status-low)';

  // Accessible screen reader label
  const accessibilityLabel = `${value} ${unit} — ${
    status === 'NORMAL' ? 'within' : status === 'LOW' ? 'below' : 'above'
  } normal reference range of ${min}–${max} ${unit}`;

  return (
    <div 
      style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '12px' }}
      title={`Reference range: ${min} - ${max} ${unit}`}
    >
      {/* Screen Reader Only text */}
      <span className="sr-only">{accessibilityLabel}</span>

      {/* Visual Indicator Bar */}
      <div 
        style={{
          position: 'relative',
          height: '6px',
          backgroundColor: 'var(--color-border)',
          borderRadius: '3px',
          width: '100%',
          overflow: 'visible'
        }}
        aria-hidden="true"
      >
        {/* Normal Range highlighted band (25% to 75%) */}
        <div 
          style={{
            position: 'absolute',
            left: '25%',
            width: '50%',
            height: '100%',
            backgroundColor: 'rgba(60, 157, 110, 0.18)',
            borderLeft: '1px solid rgba(60, 157, 110, 0.4)',
            borderRight: '1px solid rgba(60, 157, 110, 0.4)'
          }}
        />

        {/* Marker Dot */}
        <div 
          style={{
            position: 'absolute',
            left: `${positionPercent}%`,
            top: '50%',
            transform: 'translate(-50%, -50%)',
            width: '12px',
            height: '12px',
            borderRadius: '50%',
            backgroundColor: dotColor,
            border: '2px solid var(--color-bg-card)',
            boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
            zIndex: 2,
            transition: 'left 0.3s ease'
          }}
          data-testid="range-marker"
        />
      </div>

      {reference_source === 'report' && (
        <span className="caption" style={{ fontSize: '11px', textAlign: 'left' }}>
          range from your report
        </span>
      )}

      {/* Ranges label */}
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }} aria-hidden="true">
        <span className="caption" style={{ fontSize: '11px', textAlign: 'left' }}>
          {min} {unit}
        </span>
        <span className="caption" style={{ fontSize: '11px', textAlign: 'right' }}>
          {max} {unit}
        </span>
      </div>
    </div>
  );
};

export default RangeIndicator;
