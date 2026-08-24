import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RangeIndicator from '../components/dashboard/RangeIndicator';
import LabResultCard from '../components/dashboard/LabResultCard';
import LabResultTable from '../components/dashboard/LabResultTable';
import Dashboard from '../components/dashboard/Dashboard';
import { MOCK_ANALYSIS_RESULT } from '../services/api';

describe('RangeIndicator Component', () => {
  it('renders reference range values and handles missing ranges', () => {
    // 1. With range
    const { rerender } = render(
      <RangeIndicator value="14.2" ref_min={12.0} ref_max={16.0} status="NORMAL" unit="g/dL" />
    );
    expect(screen.getByText('12 g/dL')).toBeInTheDocument();
    expect(screen.getByText('16 g/dL')).toBeInTheDocument();
    expect(screen.getByTestId('range-marker')).toBeInTheDocument();

    // 2. Without range
    rerender(<RangeIndicator value="14.2" status="UNKNOWN" unit="g/dL" />);
    expect(screen.getByText('not checked against a reference range')).toBeInTheDocument();

    // 3. One-sided bound: a real range with no opposite end. 54 of the 333
    //    evaluable rows look like this (Triglycerides, LDL, HDL, PSA, CRP) and
    //    all of them used to render as "reference range unavailable" while
    //    still showing a status, which reads as a contradiction.
    rerender(
      <RangeIndicator value="3.3" ref_min={40} ref_max={null} status="LOW"
                     unit="mg/dL" reference_text=">40 mg/dL" />
    );
    expect(screen.getByText(/Normal: >40 mg\/dL/)).toBeInTheDocument();
    expect(screen.queryByText(/not checked against a reference range/)).not.toBeInTheDocument();

    // 4. Falls back to spoken wording when the backend sends no rendered text.
    rerender(
      <RangeIndicator value="180" ref_min={null} ref_max={150} status="HIGH" unit="mg/dL" />
    );
    expect(screen.getByText(/Normal: under 150 mg\/dL/)).toBeInTheDocument();
    expect(screen.queryByTestId('range-marker')).not.toBeInTheDocument();
  });

  it('calculates proportional positions based on status', () => {
    // Normal parameter (roughly middle)
    const { rerender } = render(
      <RangeIndicator value="14.0" ref_min={12.0} ref_max={16.0} status="NORMAL" unit="g/dL" />
    );
    let marker = screen.getByTestId('range-marker');
    expect(marker.style.left).toBe('50%');

    // Low parameter (left segment <= 25%)
    rerender(<RangeIndicator value="6.0" ref_min={12.0} ref_max={16.0} status="LOW" unit="g/dL" />);
    marker = screen.getByTestId('range-marker');
    const lowLeftVal = parseFloat(marker.style.left);
    expect(lowLeftVal).toBeLessThanOrEqual(25);

    // High parameter (right segment >= 75%)
    rerender(<RangeIndicator value="24.0" ref_min={12.0} ref_max={16.0} status="HIGH" unit="g/dL" />);
    marker = screen.getByTestId('range-marker');
    const highLeftVal = parseFloat(marker.style.left);
    expect(highLeftVal).toBeGreaterThanOrEqual(75);
  });
});

describe('LabResultCard Component', () => {
  const dummyResult = {
    test_name: 'Hemoglobin',
    value: '10.5',
    unit: 'g/dL',
    ref_min: 12.0,
    ref_max: 16.0,
    status: 'LOW' as const,
    explanation: 'Hemoglobin is low, indicating mild anemia.'
  };

  it('renders test values and badge status', () => {
    render(<LabResultCard result={dummyResult} />);
    expect(screen.getByText('Hemoglobin')).toBeInTheDocument();
    expect(screen.getByText('10.5')).toBeInTheDocument();
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });

  it('no longer renders the per-metric explainer accordion', () => {
    // Removed: it only ever showed "No explanations available for this metric."
    // because nothing populates LabResult.explanation.
    render(<LabResultCard result={dummyResult} />);
    expect(screen.queryByTestId('explainer-content')).not.toBeInTheDocument();
    expect(screen.queryByText(/explain this parameter/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no explanations available/i)).not.toBeInTheDocument();
  });

});

describe('LabResultTable Component', () => {
  const results = [
    { test_name: 'Hemoglobin', value: '14.2', unit: 'g/dL', ref_min: 12.0, ref_max: 16.0, status: 'NORMAL' as const, explanation: 'Normal.' },
    { test_name: 'Platelets', value: '98', unit: 'K/uL', ref_min: 150, ref_max: 450, status: 'LOW' as const, explanation: 'Low.' }
  ];

  it('renders tabular representation columns correctly', () => {
    render(<LabResultTable results={results} />);
    expect(screen.getByText('Test Parameter')).toBeInTheDocument();
    expect(screen.getByText('Your Value')).toBeInTheDocument();
    expect(screen.getByText('Reference Range')).toBeInTheDocument();

    // Rows values
    expect(screen.getByText('Hemoglobin')).toBeInTheDocument();
    expect(screen.getByText('Platelets')).toBeInTheDocument();
    expect(screen.getByText('150 - 450 K/uL')).toBeInTheDocument();
  });
});

describe('Dashboard Container Component', () => {
  const mockNewReport = vi.fn();
  const mockOpenChat = vi.fn();

  it('renders top details, files, and handles reset navigation triggers', () => {
    render(
      <Dashboard
        data={MOCK_ANALYSIS_RESULT}
        fileName="report_spec.pdf"
        onNewReport={mockNewReport}
        onOpenChat={mockOpenChat}
      />
    );

    expect(screen.getByText(/report_spec.pdf/i)).toBeInTheDocument();
    expect(screen.getByText('Total Tests')).toBeInTheDocument();

    // Click back to triggers
    fireEvent.click(screen.getByTestId('new-report-btn'));
    expect(mockNewReport).toHaveBeenCalledTimes(1);
  });

  it('filters results card list when selecting filter chips', () => {
    render(
      <Dashboard
        data={MOCK_ANALYSIS_RESULT}
        fileName="report_spec.pdf"
        onNewReport={mockNewReport}
        onOpenChat={mockOpenChat}
      />
    );

    // Initial grid has all 6 items
    const grid = screen.getByTestId('results-grid');
    expect(grid.children.length).toBe(6);

    // Click Needs Attention chip
    const needsAttentionChip = screen.getByRole('button', { name: /needs attention/i });
    fireEvent.click(needsAttentionChip);
    expect(grid.children.length).toBe(4); // 4 abnormal results in mock data (Hemoglobin, Platelets, Total Cholesterol, Vitamin D)

    // Click Normal chip
    const normalChip = screen.getByRole('button', { name: /normal \(/i });
    fireEvent.click(normalChip);
    expect(grid.children.length).toBe(2); // 2 normal results (WBC, TSH)
  });

  it('filters results using search inputs', () => {
    render(
      <Dashboard
        data={MOCK_ANALYSIS_RESULT}
        fileName="report_spec.pdf"
        onNewReport={mockNewReport}
        onOpenChat={mockOpenChat}
      />
    );

    const searchInput = screen.getByTestId('search-input');
    fireEvent.change(searchInput, { target: { value: 'wbc' } });

    const grid = screen.getByTestId('results-grid');
    expect(grid.children.length).toBe(1);
    expect(screen.getByText('WBC (White Blood Cells)')).toBeInTheDocument();
  });

  it('toggles card layout and table layout views', () => {
    render(
      <Dashboard
        data={MOCK_ANALYSIS_RESULT}
        fileName="report_spec.pdf"
        onNewReport={mockNewReport}
        onOpenChat={mockOpenChat}
      />
    );

    expect(screen.getByTestId('results-grid')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    // Toggle table
    fireEvent.click(screen.getByTestId('table-view-btn'));
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByTestId('results-grid')).not.toBeInTheDocument();

    // Toggle back to card grid
    fireEvent.click(screen.getByTestId('card-view-btn'));
    expect(screen.getByTestId('results-grid')).toBeInTheDocument();
  });

  it('triggers scrolls and focuses when medical links are clicked in explanation', () => {
    // Mock scrollIntoView in JSDOM element
    const originalScrollIntoView = window.HTMLElement.prototype.scrollIntoView;
    const mockScrollIntoView = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;

    render(
      <Dashboard
        data={MOCK_ANALYSIS_RESULT}
        fileName="report_spec.pdf"
        onNewReport={mockNewReport}
        onOpenChat={mockOpenChat}
      />
    );

    // Find a medical term link in markdown explanation, e.g., "hemoglobin" button
    const termButton = screen.getByRole('button', { name: 'Hemoglobin' });
    expect(termButton).toBeInTheDocument();

    // Click the inline term link
    fireEvent.click(termButton);

    // Should call scrollIntoView on the Hemoglobin card
    expect(mockScrollIntoView).toHaveBeenCalled();

    // Restore original prototype function
    window.HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  });
});
