import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ChatWidget from '../components/chat/ChatWidget';
import { MOCK_ANALYSIS_RESULT } from '../services/api';

describe('ChatWidget Component', () => {
  it('toggles open/close visibility on FAB clicks', () => {
    const mockToggle = vi.fn();
    const { rerender } = render(
      <ChatWidget isOpen={false} onToggle={mockToggle} reportContext={null} />
    );

    // Closed initially
    const panel = screen.getByTestId('chat-panel');
    expect(panel.style.display).toBe('none');

    // Click FAB to trigger open callback
    const fab = screen.getByTestId('chat-fab');
    fireEvent.click(fab);
    expect(mockToggle).toHaveBeenCalledTimes(1);

    // Open view state
    rerender(<ChatWidget isOpen={true} onToggle={mockToggle} reportContext={null} />);
    expect(panel.style.display).toBe('flex');
  });

  it('renders context greeting matching medical parameters', () => {
    const { rerender } = render(
      <ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={null} />
    );

    // Empty state greeting
    expect(screen.getByText(/please upload your medical report/i)).toBeInTheDocument();

    // Context populated greeting
    rerender(
      <ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={MOCK_ANALYSIS_RESULT} />
    );
    // The greeting is derived from the report actually supplied, not from a
    // hardcoded list. MOCK_ANALYSIS_RESULT contains FOUR abnormal results
    // (Hemoglobin LOW, Platelets HIGH, Cholesterol HIGH, Vitamin D LOW) even
    // though its own summary.abnormal_count says 3 - the fixture is
    // internally inconsistent. Counting the real results is the correct
    // behaviour, so this asserts 4.
    expect(screen.getByText(/4 results are outside the normal range/i)).toBeInTheDocument();
    // ...and it must name those specific tests.
    expect(screen.getByText(/Hemoglobin, Platelets, Total Cholesterol/i)).toBeInTheDocument();
    // Quick replies are likewise derived from the real abnormal results.
    expect(screen.getByText(/Explain my low Hemoglobin/i)).toBeInTheDocument();
  });

  it('does not name tests that are absent from the report', () => {
    // Regression: the greeting used to hardcode "Hemoglobin, Platelets, Total
    // Cholesterol, and Vitamin D" regardless of what was uploaded, so a patient
    // was told those were their abnormal results whatever their report said.
    const singleResult = {
      ...MOCK_ANALYSIS_RESULT,
      lab_results: [
        { test_name: 'Glucose', value: '180', unit: 'mg/dL', status: 'HIGH' as const,
          ref_min: 70, ref_max: 99 }
      ],
      summary: { total_tests: 1, abnormal_count: 1, text: 'Found 1 lab test.' }
    };
    render(<ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={singleResult} />);

    expect(screen.getByText(/1 result is outside the normal range/i)).toBeInTheDocument();
    // Glucose appears in both the greeting and a quick reply, hence getAllByText.
    expect(screen.getAllByText(/Glucose/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Vitamin D/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Platelets/i)).not.toBeInTheDocument();
  });

  it('sends user message and displays typing indicator and assistant response', async () => {
    render(<ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={MOCK_ANALYSIS_RESULT} />);

    const input = screen.getByTestId('chat-input');
    const sendBtn = screen.getByTestId('chat-send-btn');

    // Type message
    fireEvent.change(input, { target: { value: 'Should I worry about my platelets?' } });
    expect(input).toHaveValue('Should I worry about my platelets?');

    // Submit message
    fireEvent.click(sendBtn);

    // 1. User message should appear immediately
    expect(screen.getByText('Should I worry about my platelets?')).toBeInTheDocument();

    // 2. Typing indicator should show up
    expect(screen.getByTestId('typing-indicator')).toBeInTheDocument();

    // 3. Wait for mock answer to resolve (takes 1000ms in sendChatMessage mock)
    await waitFor(() => {
      expect(screen.queryByTestId('typing-indicator')).not.toBeInTheDocument();
    }, { timeout: 1500 });

    // Assistant response displayed
    expect(screen.getByText(/Platelets are key blood clotting cells/i)).toBeInTheDocument();
  });

  it('submits text immediately when clicking quick reply chips', async () => {
    render(<ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={MOCK_ANALYSIS_RESULT} />);

    const chip = screen.getByRole('button', { name: /Explain my low Hemoglobin/i });
    expect(chip).toBeInTheDocument();

    // Click chip
    fireEvent.click(chip);

    // User message should appear immediately
    expect(screen.getByText('Explain my low Hemoglobin')).toBeInTheDocument();

    // Wait for response to resolve
    await waitFor(() => {
      expect(screen.getByText(/Hemoglobin carries oxygen/i)).toBeInTheDocument();
    }, { timeout: 1500 });
  });

  it('shows error warning card and handles retries upon API failures', async () => {
    render(<ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={MOCK_ANALYSIS_RESULT} />);

    const input = screen.getByTestId('chat-input');
    const sendBtn = screen.getByTestId('chat-send-btn');

    // Input trigger keyword
    fireEvent.change(input, { target: { value: 'trigger api error' } });
    fireEvent.click(sendBtn);

    // Expect connection error card
    await waitFor(() => {
      expect(screen.getByTestId('chat-error')).toBeInTheDocument();
    }, { timeout: 1500 });

    expect(screen.getByText(/Network connection failed/i)).toBeInTheDocument();

    // Click retry
    const retryBtn = screen.getByRole('button', { name: /retry question/i });
    fireEvent.click(retryBtn);

    // Expect error card cleared and typing indicator back
    expect(screen.queryByTestId('chat-error')).not.toBeInTheDocument();
    expect(screen.getByTestId('typing-indicator')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByTestId('typing-indicator')).not.toBeInTheDocument();
    }, { timeout: 1500 });
  });
});

describe('ChatWidget markdown rendering', () => {
  it('renders malformed model markdown without leaking asterisks', async () => {
    // A real reply from the deployed model. The bullet is spurious, "**" is
    // opened and a single "*" closes it, so a balanced-only parser matched
    // nothing and showed the patient the raw markers.
    const malformed =
      '* **An anion gap is a measure of the difference between ions. ' +
      'A low anion gap may need to be discussed with a clinician.*';

    const api = await import('../services/api');
    const spy = vi
      .spyOn(api, 'sendChatMessage')
      .mockResolvedValue(malformed);

    render(<ChatWidget isOpen={true} onToggle={vi.fn()} reportContext={null} />);

    const input = screen.getByTestId('chat-input');
    fireEvent.change(input, { target: { value: 'what is an anion gap?' } });
    fireEvent.click(screen.getByTestId('chat-send-btn'));

    await waitFor(() => {
      expect(screen.getByText(/An anion gap is a measure/)).toBeInTheDocument();
    }, { timeout: 2000 });

    const panel = screen.getByTestId('chat-panel');
    expect(panel.textContent).not.toContain('*');
    spy.mockRestore();
  });
});
