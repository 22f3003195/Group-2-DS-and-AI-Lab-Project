import React from 'react';
import Badge from '../shared/Badge';
import { describeReason } from '../../services/api';
import type { LabResult } from '../../services/api';

export interface LabResultTableProps {
  results: LabResult[];
  highlightedTests?: Record<string, boolean>;
}

export const LabResultTable: React.FC<LabResultTableProps> = ({ 
  results,
  highlightedTests = {}
}) => {
  // Helpers to fetch background tints based on status for table rows (6% opacity)
  const getRowBgColor = (status: 'HIGH' | 'LOW' | 'NORMAL' | 'UNKNOWN') => {
    switch (status) {
      case 'HIGH':
        return 'rgba(217, 83, 79, 0.06)';
      case 'LOW':
        return 'rgba(224, 151, 59, 0.06)';
      case 'NORMAL':
        return 'transparent';
      default:
        return 'rgba(138, 151, 160, 0.03)';
    }
  };

  const getBorderColor = (testName: string) => {
    return highlightedTests[testName] ? '2px solid var(--color-secondary-accent)' : '1px solid var(--color-border)';
  };

  return (
    <div style={{
      width: '100%',
      overflowX: 'auto',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-card)',
      backgroundColor: 'var(--color-bg-card)',
      boxShadow: 'var(--shadow-soft)'
    }}>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        textAlign: 'left',
        fontSize: '14px',
        minWidth: '500px'
      }}>
        <thead>
          <tr style={{
            borderBottom: '1px solid var(--color-border)',
            backgroundColor: 'var(--color-bg-app)',
            position: 'sticky',
            top: 0,
            zIndex: 10
          }}>
            <th style={{ padding: '16px 20px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>Test Parameter</th>
            <th style={{ padding: '16px 20px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>Your Value</th>
            <th style={{ padding: '16px 20px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>Reference Range</th>
            <th style={{ padding: '16px 20px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            // Prefer the backend's rendered range: it handles one-sided bounds
            // ("<150 mg/dL") and sex-specific ranges that min/max cannot express.
            // Unchecked results show the reason, never a range (see RangeIndicator).
            const rangeLabel = result.status === 'UNKNOWN' ? null
              : result.reference_text
              || (result.ref_min != null && result.ref_max != null
                    ? `${result.ref_min} - ${result.ref_max} ${result.unit}`
                    : null);
            const isHighlighted = highlightedTests[result.test_name];

            return (
              <tr 
                key={result.test_name} 
                style={{
                  borderBottom: '1px solid var(--color-border)',
                  backgroundColor: getRowBgColor(result.status),
                  outline: isHighlighted ? '2px solid var(--color-secondary-accent)' : 'none',
                  outlineOffset: '-2px',
                  transition: 'background-color 0.2s ease'
                }}
              >
                {/* Parameter Name */}
                <td style={{ padding: '16px 20px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                  {result.test_name}
                </td>
                
                {/* Patient Value */}
                <td className="number-tabular" style={{ padding: '16px 20px', fontSize: '15px', color: 'var(--color-text-primary)' }}>
                  {result.value} <span className="caption" style={{ fontSize: '12px', fontWeight: 400 }}>{result.unit}</span>
                </td>
                
                {/* Normal Boundaries */}
                <td style={{ padding: '16px 20px', color: 'var(--color-text-secondary)' }}>
                  {rangeLabel ?? (
                    <span title={describeReason(result.reason)} style={{ fontStyle: 'italic' }}>
                      {describeReason(result.reason)}
                    </span>
                  )}
                </td>
                
                {/* Status Badging */}
                <td style={{ padding: '16px 20px' }}>
                  <Badge status={result.status} reason={describeReason(result.reason)} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default LabResultTable;
