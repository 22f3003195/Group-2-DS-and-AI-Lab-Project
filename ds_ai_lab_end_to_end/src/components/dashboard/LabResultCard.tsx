import React from 'react';
import Card from '../shared/Card';
import Badge from '../shared/Badge';
import RangeIndicator from './RangeIndicator';
import type { LabResult } from '../../services/api';

export interface LabResultCardProps {
  result: LabResult;
  isHighlighted?: boolean;
}

export const LabResultCard: React.FC<LabResultCardProps> = ({ result, isHighlighted = false }) => {
  const highlightStyle = isHighlighted
    ? {
        border: '2px solid var(--color-secondary-accent)',
        backgroundColor: 'rgba(91, 107, 247, 0.03)',
        transform: 'scale(1.02)'
      }
    : {};

  return (
    <Card
      style={{
        ...highlightStyle,
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-12)',
        padding: 'var(--space-16)',
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        position: 'relative'
      }}
      aria-label={`${result.test_name}: ${result.value} ${result.unit}, ${result.status}`}
      data-testid={`result-card-${result.test_name.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Top row: Name + Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%', gap: '8px' }}>
        <span 
          style={{ 
            fontWeight: 600, 
            fontSize: '15px', 
            color: 'var(--color-text-primary)',
            textAlign: 'left',
            lineHeight: '20px'
          }}
        >
          {result.test_name}
        </span>
        <Badge status={result.status} />
      </div>

      {/* Numerical Value */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px', textAlign: 'left', marginTop: '4px' }}>
        <span className="number-tabular" style={{ fontSize: '28px', color: 'var(--color-text-primary)' }}>
          {result.value}
        </span>
        <span className="caption" style={{ fontSize: '14px', fontWeight: 500 }}>
          {result.unit}
        </span>
      </div>

      {/* Range Indicator */}
      <RangeIndicator
        value={result.value}
        ref_min={result.ref_min}
        ref_max={result.ref_max}
        status={result.status}
        unit={result.unit}
        reference_text={result.reference_text}
        reference_source={result.reference_source}
      />

    </Card>
  );
};

export default LabResultCard;
