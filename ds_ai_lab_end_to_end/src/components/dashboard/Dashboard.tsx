import React, { useState, useMemo, useEffect } from 'react';
import { LayoutGrid, TableProperties, Search, ArrowLeft, Download, Trash2, HelpCircle } from 'lucide-react';
import Button from '../shared/Button';
import LabResultCard from './LabResultCard';
import LabResultTable from './LabResultTable';
import type { AnalysisResponse, LabResult } from '../../services/api';

// Markdown renderer helper
interface MarkdownProps {
  content: string;
  onTermClick?: (termName: string) => void;
}

export const MarkdownRenderer: React.FC<MarkdownProps> = ({ content, onTermClick }) => {
  const lines = content.split('\n');

  // Inline bold/highlight parser helper
  const parseInlineStyles = (text: string) => {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        const boldText = part.slice(2, -2);
        
        // Find matching term name
        const lowerBold = boldText.toLowerCase();
        const matchesMedicalTerm = ['hemoglobin', 'platelets', 'cholesterol', 'vitamin d', 'wbc', 'tsh'].some(
          (term) => lowerBold.includes(term)
        );

        if (matchesMedicalTerm && onTermClick) {
          let canonical = boldText;
          if (lowerBold.includes('hemoglobin')) canonical = 'Hemoglobin';
          else if (lowerBold.includes('platelets')) canonical = 'Platelets';
          else if (lowerBold.includes('cholesterol')) canonical = 'Total Cholesterol';
          else if (lowerBold.includes('vitamin d')) canonical = 'Vitamin D, 25-Hydroxy';
          else if (lowerBold.includes('wbc') || lowerBold.includes('white blood')) canonical = 'WBC (White Blood Cells)';
          else if (lowerBold.includes('tsh') || lowerBold.includes('thyroid')) canonical = 'TSH (Thyroid Stimulating Hormone)';

          return (
            <button
              key={index}
              onClick={() => onTermClick(canonical)}
              className="btn--highlight-term"
              style={{
                background: 'rgba(91, 107, 247, 0.08)',
                border: 'none',
                borderBottom: '2px dashed var(--color-secondary-accent)',
                color: 'var(--color-text-primary)',
                fontWeight: 600,
                cursor: 'pointer',
                padding: '0 4px',
                borderRadius: '2px',
                fontSize: 'inherit',
                fontFamily: 'inherit',
                display: 'inline',
                margin: 0
              }}
              title={`Click to highlight ${canonical} card`}
            >
              {boldText}
            </button>
          );
        }
        return <strong key={index} style={{ fontWeight: 700 }}>{boldText}</strong>;
      }
      return part;
    });
  };

  return (
    <div style={{ lineHeight: '26px', fontSize: '15px', color: 'var(--color-text-primary)' }}>
      {lines.map((line, idx) => {
        const trimmed = line.trim();

        if (trimmed.startsWith('## ')) {
          return <h3 key={idx} className="h3" style={{ marginTop: '24px', marginBottom: '12px' }}>{trimmed.slice(3)}</h3>;
        }
        if (trimmed.startsWith('### ')) {
          return <h4 key={idx} className="h3" style={{ fontSize: '16px', marginTop: '18px', marginBottom: '8px' }}>{trimmed.slice(4)}</h4>;
        }
        if (trimmed.startsWith('# ')) {
          return <h2 key={idx} className="h2" style={{ marginTop: '32px', marginBottom: '16px' }}>{trimmed.slice(2)}</h2>;
        }
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
          return (
            <li key={idx} style={{ marginLeft: '20px', marginBottom: '8px', listStyleType: 'disc' }}>
              {parseInlineStyles(trimmed.slice(2))}
            </li>
          );
        }
        if (trimmed === '') {
          return <div key={idx} style={{ height: '12px' }} />;
        }
        return (
          <p key={idx} style={{ marginBottom: '16px', maxWidth: '720px' }}>
            {parseInlineStyles(trimmed)}
          </p>
        );
      })}
    </div>
  );
};

export interface DashboardProps {
  data: AnalysisResponse;
  fileName: string;
  onNewReport: () => void;
  onOpenChat?: () => void;
}

type FilterType = 'all' | 'needs-attention' | 'normal';
type SortType = 'status' | 'alpha' | 'listed';
type ViewType = 'card' | 'table';

export const Dashboard: React.FC<DashboardProps> = ({
  data,
  fileName,
  onNewReport,
  onOpenChat
}) => {
  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortType>('status');
  const [view, setView] = useState<ViewType>('card');
  const [highlightedTest, setHighlightedTest] = useState<string | null>(null);

  // Statistics details
  const totalTests = data.lab_results.length;
  const abnormalTests = data.lab_results.filter(r => r.status === 'HIGH' || r.status === 'LOW');
  const normalTestsCount = data.lab_results.filter(r => r.status === 'NORMAL').length;
  const abnormalCount = abnormalTests.length;
  const unknownCount = data.lab_results.filter(r => r.status === 'UNKNOWN').length;

  // Segment widths for proportion distribution bar
  const normalPercent = totalTests > 0 ? (normalTestsCount / totalTests) * 100 : 0;
  const abnormalPercent = totalTests > 0 ? (abnormalCount / totalTests) * 100 : 0;
  const unknownPercent = totalTests > 0 ? (unknownCount / totalTests) * 100 : 0;

  // Clear outline highlights after delay
  const handleTermClick = (termName: string) => {
    setHighlightedTest(termName);
    
    // Find visual element and scroll into view smoothly
    const normalizedId = termName.toLowerCase().replace(/\s+/g, '-');
    const targetElement = document.querySelector(`[data-testid="result-card-${normalizedId}"]`);
    if (targetElement) {
      targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    setTimeout(() => {
      setHighlightedTest(null);
    }, 2000);
  };

  // Perform search filters & sorting
  const processedResults = useMemo(() => {
    let list = [...data.lab_results];

    // Search query matches parameter names
    if (search.trim() !== '') {
      list = list.filter(r => r.test_name.toLowerCase().includes(search.toLowerCase()));
    }

    // Filter chip matches
    if (filter === 'needs-attention') {
      list = list.filter(r => r.status === 'HIGH' || r.status === 'LOW');
    } else if (filter === 'normal') {
      list = list.filter(r => r.status === 'NORMAL');
    }

    // Sort order mapping
    if (sortBy === 'alpha') {
      list.sort((a, b) => a.test_name.localeCompare(b.test_name));
    } else if (sortBy === 'status') {
      const score = { 'HIGH': 3, 'LOW': 2, 'UNKNOWN': 1, 'NORMAL': 0 };
      list.sort((a, b) => score[b.status] - score[a.status]);
    }

    return list;
  }, [data.lab_results, search, filter, sortBy]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-24)', padding: '0 0 var(--space-40) 0' }}>
      
      {/* Top dashboard controls header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 'var(--space-12)',
        borderBottom: '1px solid var(--color-border)',
        paddingBottom: '16px'
      }}>
        {/* Left side: back button */}
        <button
          className="btn btn--ghost flex-row"
          onClick={onNewReport}
          style={{ paddingLeft: 0, fontWeight: 500 }}
          data-testid="new-report-btn"
        >
          <ArrowLeft size={16} /> New report
        </button>

        {/* Middle: File info metadata */}
        <div className="caption" style={{ fontSize: '13px', fontWeight: 500 }}>
          📄 {fileName} &bull; Uploaded {new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
        </div>

        {/* Right side: Action stubs */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="ghost" className="flex-row" style={{ fontSize: '13px', padding: '6px 12px' }} title="Download summary as PDF">
            <Download size={14} /> PDF
          </Button>
          <Button variant="ghost" className="flex-row" style={{ fontSize: '13px', padding: '6px 12px', color: 'var(--color-status-high)' }} title="Delete this report">
            <Trash2 size={14} /> Delete
          </Button>
        </div>
      </div>

      {/* Main Two-Zone Layout Container */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-32)' }}>
        
        {/* Zone 1: Overview Summary Header */}
        <div className="card" style={{ padding: 'var(--space-24)', display: 'flex', flexDirection: 'column', gap: 'var(--space-24)' }}>
          {/* Big Alert Banner */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-12)', textAlign: 'left' }}>
            <div style={{
              width: '10px',
              height: '40px',
              borderRadius: '4px',
              backgroundColor: abnormalCount > 0 ? 'var(--color-status-low)' : 'var(--color-status-normal)'
            }} />
            <h2 className="h2" style={{ fontSize: '20px' }}>
              {abnormalCount === 0 
                ? 'Everything in this report looks within normal range.' 
                : `We found ${abnormalCount} result(s) outside the normal range.`
              }
            </h2>
          </div>

          {/* 3 Stat Tiles */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 'var(--space-16)'
          }}>
            {/* Tile 1: Total */}
            <div 
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-btn)',
                padding: '16px',
                textAlign: 'left',
                backgroundColor: 'rgba(0,0,0,0.01)'
              }}
            >
              <span className="caption" style={{ fontSize: '12px', fontWeight: 600 }}>Total Tests</span>
              <div className="number-tabular" style={{ fontSize: '28px', marginTop: '4px', color: 'var(--color-text-primary)' }}>{totalTests}</div>
            </div>

            {/* Tile 2: Normal */}
            <div 
              onClick={() => setFilter('normal')}
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-btn)',
                padding: '16px',
                textAlign: 'left',
                backgroundColor: 'rgba(0,0,0,0.01)',
                cursor: 'pointer',
                outline: filter === 'normal' ? '2px solid var(--color-status-normal)' : 'none'
              }}
              data-testid="stat-tile-normal"
            >
              <span className="caption" style={{ fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-status-normal)' }} /> Normal
              </span>
              <div className="number-tabular" style={{ fontSize: '28px', marginTop: '4px', color: 'var(--color-status-normal)' }}>{normalTestsCount}</div>
            </div>

            {/* Tile 3: Needs Attention */}
            <div 
              onClick={() => setFilter('needs-attention')}
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-btn)',
                padding: '16px',
                textAlign: 'left',
                backgroundColor: 'rgba(0,0,0,0.01)',
                cursor: 'pointer',
                outline: filter === 'needs-attention' ? '2px solid var(--color-status-low)' : 'none'
              }}
              data-testid="stat-tile-abnormal"
            >
              <span className="caption" style={{ fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-status-low)' }} /> Needs Attention
              </span>
              <div className="number-tabular" style={{ fontSize: '28px', marginTop: '4px', color: 'var(--color-status-low)' }}>{abnormalCount}</div>
            </div>
          </div>

          {/* Segmented Status Distribution Bar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{
              height: '8px',
              width: '100%',
              borderRadius: '4px',
              overflow: 'hidden',
              display: 'flex',
              backgroundColor: 'var(--color-border)'
            }}>
              <div style={{ width: `${normalPercent}%`, backgroundColor: 'var(--color-status-normal)', height: '100%' }} title={`Normal: ${normalTestsCount}`} />
              <div style={{ width: `${abnormalPercent}%`, backgroundColor: 'var(--color-status-low)', height: '100%' }} title={`Abnormal: ${abnormalCount}`} />
              <div style={{ width: `${unknownPercent}%`, backgroundColor: 'var(--color-status-unknown)', height: '100%' }} title={`Unknown: ${unknownCount}`} />
            </div>
          </div>
        </div>

        {/* Zone 2: Lab Results Parameter Grid & Search */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-16)' }}>
          {/* Controls Bar */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 'var(--space-16)',
            marginBottom: '4px'
          }}>
            {/* Filter chips left */}
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }} data-testid="filter-chips">
              <button 
                onClick={() => setFilter('all')}
                className="btn"
                style={{
                  padding: '6px 12px',
                  fontSize: '13px',
                  backgroundColor: filter === 'all' ? 'var(--color-primary)' : 'var(--color-bg-card)',
                  color: filter === 'all' ? '#FFFFFF' : 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)'
                }}
              >
                All ({totalTests})
              </button>
              <button 
                onClick={() => setFilter('needs-attention')}
                className="btn"
                style={{
                  padding: '6px 12px',
                  fontSize: '13px',
                  backgroundColor: filter === 'needs-attention' ? 'var(--color-status-low)' : 'var(--color-bg-card)',
                  color: filter === 'needs-attention' ? '#FFFFFF' : 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)'
                }}
              >
                Needs Attention ({abnormalCount})
              </button>
              <button 
                onClick={() => setFilter('normal')}
                className="btn"
                style={{
                  padding: '6px 12px',
                  fontSize: '13px',
                  backgroundColor: filter === 'normal' ? 'var(--color-status-normal)' : 'var(--color-bg-card)',
                  color: filter === 'normal' ? '#FFFFFF' : 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)'
                }}
              >
                Normal ({normalTestsCount})
              </button>
            </div>

            {/* Search/Sort Right */}
            <div style={{ display: 'flex', gap: 'var(--space-12)', alignItems: 'center', flexWrap: 'wrap', flex: 1, justifyContent: 'flex-end' }}>
              {/* Search Box */}
              <div style={{ position: 'relative', width: '220px' }}>
                <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-secondary)' }} />
                <input 
                  type="text"
                  placeholder="Search test..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="form-input"
                  style={{
                    paddingLeft: '32px',
                    paddingTop: '6px',
                    paddingBottom: '6px',
                    fontSize: '13px',
                    width: '100%'
                  }}
                  data-testid="search-input"
                />
              </div>

              {/* Sort selector */}
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortType)}
                className="form-input"
                style={{ paddingTop: '6px', paddingBottom: '6px', fontSize: '13px', cursor: 'pointer' }}
                data-testid="sort-select"
              >
                <option value="status">Sort by Status</option>
                <option value="alpha">Alphabetical</option>
                <option value="listed">As listed in report</option>
              </select>

              {/* View layout Toggle */}
              <div style={{
                display: 'flex',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-btn)',
                overflow: 'hidden',
                backgroundColor: 'var(--color-bg-card)'
              }}>
                <button
                  onClick={() => setView('card')}
                  style={{
                    padding: '6px 10px',
                    border: 'none',
                    backgroundColor: view === 'card' ? 'rgba(15, 110, 110, 0.08)' : 'transparent',
                    color: view === 'card' ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                    cursor: 'pointer'
                  }}
                  title="Card view"
                  data-testid="card-view-btn"
                >
                  <LayoutGrid size={16} />
                </button>
                <button
                  onClick={() => setView('table')}
                  style={{
                    padding: '6px 10px',
                    border: 'none',
                    backgroundColor: view === 'table' ? 'rgba(15, 110, 110, 0.08)' : 'transparent',
                    color: view === 'table' ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                    cursor: 'pointer'
                  }}
                  title="Table view"
                  data-testid="table-view-btn"
                >
                  <TableProperties size={16} />
                </button>
              </div>
            </div>
          </div>

          {/* Results Grid List */}
          <div>
            {processedResults.length === 0 ? (
              <div className="card" style={{ padding: 'var(--space-32)', textAlign: 'center' }}>
                <p className="body-secondary">No parameter matches your filters or search query.</p>
                <button 
                  className="btn btn--ghost" 
                  onClick={() => { setFilter('all'); setSearch(''); }}
                  style={{ marginTop: '8px', textDecoration: 'underline' }}
                >
                  Clear all filters
                </button>
              </div>
            ) : view === 'card' ? (
              <div className="grid-3" style={{ gap: '16px' }} data-testid="results-grid">
                {processedResults.map((res) => (
                  <LabResultCard 
                    key={res.test_name} 
                    result={res} 
                    isHighlighted={highlightedTest === res.test_name}
                  />
                ))}
              </div>
            ) : (
              <LabResultTable 
                results={processedResults} 
                highlightedTests={highlightedTest ? { [highlightedTest]: true } : {}}
              />
            )}
          </div>
        </div>

        {/* Zone 3: AI Explanation Prose Narrative */}
        <div className="card" style={{ padding: 'var(--space-24)', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 'var(--space-16)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--color-border)', paddingBottom: '12px' }}>
            <h2 className="h2" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              What This Means For You
            </h2>
            <span 
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--color-secondary-accent)',
                backgroundColor: 'rgba(91, 107, 247, 0.08)',
                padding: '2px 8px',
                borderRadius: '4px'
              }}
              title="This narrative breakdown is generated using a clinical translation AI language model."
            >
              🤖 AI-GENERATED
            </span>
          </div>

          <div style={{ maxWidth: '720px' }}>
            <MarkdownRenderer 
              content={data.patient_explanation} 
              onTermClick={handleTermClick}
            />
          </div>

          {/* Interactive Chat Bridge */}
          <div style={{
            marginTop: '16px',
            backgroundColor: 'rgba(15, 110, 110, 0.02)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-btn)',
            padding: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 'var(--space-12)'
          }}>
            <div style={{ textAlign: 'left' }}>
              <p style={{ fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: '4px' }}>
                Have a question about your results?
              </p>
              <p className="caption" style={{ fontSize: '13px' }}>
                Our virtual assistant is ready to explain individual metrics or provide health tips.
              </p>
            </div>
            {onOpenChat && (
              <Button variant="primary" onClick={onOpenChat} className="flex-row">
                <HelpCircle size={16} /> Ask Assistant
              </Button>
            )}
          </div>

          {/* Medical Disclaimer */}
          <p className="caption" style={{ fontSize: '12px', marginTop: '8px', lineHeight: '18px' }}>
            <strong>Disclaimer:</strong> This explanation is generated by AI based on your uploaded report and is for informational purposes only. It is not a clinical diagnosis or medical substitute. Always discuss your results with a qualified healthcare provider.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
