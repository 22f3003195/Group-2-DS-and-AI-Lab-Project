import { Client } from "@gradio/client";

export type LabStatus = 'HIGH' | 'LOW' | 'NORMAL' | 'UNKNOWN';

/** Why a result could not be evaluated. Mirrors the backend's reason codes. */
export const NOT_EVALUATED_REASONS: Record<string, string> = {
  TEST_NOT_IN_REFERENCE_TABLE: 'Not in our reference table',
  TEST_NOT_FOUND: 'Test name not recognised',
  UNIT_MISMATCH: "Units don't match our reference table",
  UNIT_ON_UNITLESS_TEST: 'This is a ratio or index — it has no units',
  SUSPECTED_UNIT_MISMATCH: 'Units look unusual for this test',
  MISSING_UNIT: 'No unit on the report',
  QUALITATIVE_ANALYTE: 'Reported as a description, not a number',
  BODY_FLUID_NO_FIXED_RANGE: 'Read against a matching blood sample',
  NO_STANDARDIZED_RANGE: 'No standard range exists',
  NOMOGRAM_REQUIRED: 'Read against an age chart',
  AMBIGUOUS_PEAK_TROUGH: 'Depends on dose timing',
  SEX_REQUIRED: 'Needs patient sex to interpret',
  AMBIGUOUS_MATCH: 'Matches more than one test — two rows may have been read as one',
  NO_NUMERIC_VALUE: 'No numeric value found',
};

export interface LabResult {
  test_name: string;
  value: string;
  unit: string;
  status: LabStatus;
  ref_min?: number | null;
  ref_max?: number | null;
  /** Human-readable range, e.g. "13.2-16.6 g/dL". Preferred over ref_min/max. */
  reference_text?: string | null;
  /** Set when status is UNKNOWN: the machine-readable reason it wasn't evaluated. */
  reason?: string | null;
  /** Conditions the patient must see, e.g. "sex not provided; combined range used". */
  caveats?: string[];
  /** 'report' when the range came from the patient's own report rather than our table. */
  reference_source?: 'table' | 'report' | null;
  explanation?: string;
}

/** Turn a backend reason code into something a patient can read. */
export const describeReason = (reason?: string | null): string =>
  (reason && NOT_EVALUATED_REASONS[reason]) || 'Could not be checked';

export interface ReportSummary {
  total_tests: number;
  abnormal_count: number;
  text: string;
}

export interface AnalysisResponse {
  success: boolean;
  lab_results: LabResult[];
  summary: ReportSummary;
  patient_explanation: string;
}

export const MOCK_ANALYSIS_RESULT: AnalysisResponse = {
  success: true,
  lab_results: [
    {
      test_name: 'Hemoglobin',
      value: '10.2',
      unit: 'g/dL',
      status: 'LOW',
      ref_min: 12.0,
      ref_max: 16.0,
      explanation: 'Hemoglobin is the protein in red blood cells that carries oxygen. A low level means your body is receiving less oxygen, which can lead to fatigue, weakness, or anemia.'
    },
    {
      test_name: 'WBC (White Blood Cells)',
      value: '7.8',
      unit: '10^9/L',
      status: 'NORMAL',
      ref_min: 4.5,
      ref_max: 11.0,
      explanation: 'White blood cells are the core of your immune system. Your level is healthy, suggesting no active bacterial infections or severe inflammation.'
    },
    {
      test_name: 'Platelets',
      value: '520',
      unit: '10^9/L',
      status: 'HIGH',
      ref_min: 150,
      ref_max: 450,
      explanation: 'Platelets are responsible for helping your blood clot when you have a cut. A high count can sometimes be a temporary reaction to inflammation, iron deficiency, or infection.'
    },
    {
      test_name: 'Total Cholesterol',
      value: '240',
      unit: 'mg/dL',
      status: 'HIGH',
      ref_min: 100,
      ref_max: 200,
      explanation: 'Total cholesterol measures the fats in your blood. A high reading suggests a need to monitor your diet, exercise, or speak with your doctor about cardiovascular health.'
    },
    {
      test_name: 'Vitamin D, 25-Hydroxy',
      value: '18',
      unit: 'ng/mL',
      status: 'LOW',
      ref_min: 30,
      ref_max: 100,
      explanation: 'Vitamin D is crucial for maintaining strong bones and supporting immune defense. A value below 20 ng/mL points to a deficiency, which might benefit from sunlight exposure or supplements.'
    },
    {
      test_name: 'TSH (Thyroid Stimulating Hormone)',
      value: '2.1',
      unit: 'uIU/mL',
      status: 'NORMAL',
      ref_min: 0.4,
      ref_max: 4.5,
      explanation: 'TSH regulates your thyroid gland which controls your metabolism. Your value is normal, indicating healthy thyroid activity.'
    }
  ],
  summary: {
    total_tests: 6,
    abnormal_count: 3,
    text: 'Found 6 lab tests. 3 results require attention.'
  },
  patient_explanation: `## Your Results Overview

We analyzed your medical report and extracted **6 key test results**. Overall, **3 values are outside the normal reference ranges** (Hemoglobin, Platelets, and Total Cholesterol). The rest of your numbers, including White Blood Cell count and TSH, look healthy and normal.

Here is a breakdown of what this means for you:

### 1. Oxygen Levels & Red Blood Cells (LOW Hemoglobin)
Your **Hemoglobin** level is **10.2 g/dL**, which is below the normal range of **12.0–16.0 g/dL**. Hemoglobin is the iron-rich protein that helps red blood cells carry oxygen. A low level is common and often indicates mild anemia. This can cause you to feel more tired than usual or feel short of breath during exercise.

### 2. Blood Clotting Elements (HIGH Platelets)
Your **Platelet count** is **520 10^9/L**, which is slightly upper the upper normal limit of **450 10^9/L**. Platelets help your blood seal cuts. A high count can sometimes result from minor inflammation, iron deficiency, or recent stress on the body.

### 3. Cholesterol & Heart Health (HIGH Cholesterol)
Your **Total Cholesterol** is **240 mg/dL** (ideal is under **200 mg/dL**). While elevated cholesterol does not cause immediate symptoms, managing it through balanced meals, regular physical activity, and consulting with your doctor is important for long-term arterial health.

### 4. Bone & Immune Health (LOW Vitamin D)
Your **Vitamin D** is **18 ng/mL**, falling below the healthy target of **30 ng/mL**. Vitamin D deficiency is highly common and can cause muscle fatigue or low bone density. This can be improved with diet, safe sun exposure, or over-the-counter supplements.`
};

export interface PipelineStep {
  id: number;
  text: string;
  duration: number; // in ms
}

export const PIPELINE_STEPS: PipelineStep[] = [
  { id: 1, text: 'Extracting text (OCR)', duration: 1500 },
  { id: 2, text: 'Identifying your test results (AI)', duration: 1500 },
  { id: 3, text: 'Organizing your results', duration: 1000 },
  { id: 4, text: 'Writing your plain-language explanation', duration: 2500 }
];

const IS_TEST = typeof window === 'undefined' || (typeof (globalThis as any).process !== 'undefined' && (globalThis as any).process.env?.NODE_ENV === 'test');

let clientInstance: Client | null = null;

// Where to send requests. Defaults to the public proxy Space; point it at a
// locally running backend to develop against uncommitted changes:
//
//   VITE_GRADIO_ENDPOINT=http://127.0.0.1:7860
//   VITE_ANALYZE_API=/analyze_report
//
// Safe to expose: a Space name is not a credential. This is exactly why the
// token lives on the proxy instead - anything VITE_-prefixed is inlined into
// the client bundle and readable by every visitor, so a token must never be
// passed this way.
const GRADIO_ENDPOINT =
  import.meta.env?.VITE_GRADIO_ENDPOINT || "rajsri2609/medical-report-ai-proxy";

// The proxy publishes /analyze; the backend Space itself publishes
// /analyze_report. Both publish /chat with the same signature.
const ANALYZE_API = import.meta.env?.VITE_ANALYZE_API || "/analyze";

async function getClient(): Promise<Client> {
  if (!clientInstance) {
    clientInstance = await Client.connect(GRADIO_ENDPOINT);
  }
  return clientInstance;
}

export const analyzeReport = (
  file: File,
  onStepChange: (stepId: number, status: 'done' | 'active' | 'upcoming') => void
): Promise<AnalysisResponse> => {
  return new Promise((resolve, reject) => {
    // Basic file validation. In `npm run dev` a .txt of report text is also
    // accepted, to pair with the backend's MEDREPORT_STUB_MODELS=1 mode; the
    // production build never allows it.
    const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
    if (import.meta.env?.DEV) validTypes.push('text/plain');
    const maxSize = 10 * 1024 * 1024; // 10MB

    if (!validTypes.includes(file.type)) {
      setTimeout(() => reject(new Error('That file type isn\'t supported — please upload a JPG, PNG, or PDF.')), 200);
      return;
    }

    if (file.size > maxSize) {
      setTimeout(() => reject(new Error('That file is too large — please upload something under 10MB.')), 200);
      return;
    }

    // NOTE: filename-based failure simulation was removed here. It rejected any
    // upload whose name contained "fail", "corrupt" or "empty" before calling
    // the API, so a real report named e.g. heart-failure-panel.pdf could never
    // be analysed. Real OCR and extraction errors surface from the backend.

    // Stepper animations configuration
    // The stepper is presentational only. It must never gate the result: the
    // previous version summed to a fixed 6.5s and resolved only after the
    // animation finished, so a fast response still waited, and a slow one
    // showed a completed progress list while polling every 100ms.
    let currentStepIndex = 0;
    let settled = false;
    let stepTimer: ReturnType<typeof setTimeout> | null = null;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      if (stepTimer) clearTimeout(stepTimer);
      PIPELINE_STEPS.forEach(s => onStepChange(s.id, 'done'));
      fn();
    };

    const executeStep = () => {
      if (settled || currentStepIndex >= PIPELINE_STEPS.length) return;

      const step = PIPELINE_STEPS[currentStepIndex];
      onStepChange(step.id, 'active');
      for (let i = 0; i < currentStepIndex; i++) onStepChange(PIPELINE_STEPS[i].id, 'done');
      for (let i = currentStepIndex + 1; i < PIPELINE_STEPS.length; i++) onStepChange(PIPELINE_STEPS[i].id, 'upcoming');

      stepTimer = setTimeout(() => {
        onStepChange(step.id, 'done');
        currentStepIndex++;
        // Hold on the last step while a slow backend (or a cold ZeroGPU start)
        // is still working, instead of showing a finished list.
        if (currentStepIndex < PIPELINE_STEPS.length) executeStep();
      }, step.duration);
    };

    if (IS_TEST) {
      // For local vitest runner, call the original mocked API
      const formData = new FormData();
      formData.append("file", file);
      fetch("http://127.0.0.1:8000/api/reports/analyze", {
        method: "POST",
        body: formData
      })
        .then(async (res) => {
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Server error analyzing file");
          }
          return res.json();
        })
        .then((data) => {
          const formattedData: AnalysisResponse = {
            success: data.report.success,
            lab_results: data.report.lab_results,
            summary: data.report.summary,
            patient_explanation: data.summary
          };
          finish(() => resolve(formattedData));
        })
        .catch((err) => {
          console.error("Backend server connection failed.", err);
          finish(() => reject(err));
        });
        
      executeStep();
      return;
    }

    // Call real Hugging Face Space endpoints using Gradio Client in browser
    getClient()
      .then(async (client) => {
        const response = await client.predict(ANALYZE_API, [file]);
        const data = (response as any).data[0];
        
        if (!data || !data.report || !data.report.success) {
          throw new Error("No lab results were detected in this report. Verify it is a valid laboratory report.");
        }

        const formattedData: AnalysisResponse = {
          success: data.report.success,
          lab_results: data.report.lab_results,
          summary: data.report.summary,
          patient_explanation: data.summary
        };
        finish(() => resolve(formattedData));
      })
      .catch((err) => {
        console.error("Gradio analysis failed:", err);
        let friendlyMessage = "We couldn't analyze the report. Please try again.";
        const errMsg = err.message || "";
        if (errMsg.includes("401") || errMsg.includes("403") || errMsg.includes("access") || errMsg.includes("unauthorized")) {
          friendlyMessage = "Access Denied (401/403) from proxy. Please verify the Space visibility or token on the proxy server.";
        } else if (errMsg.includes("sleeping")) {
          friendlyMessage = "The AI proxy Space is currently waking up. Please wait about 30 seconds and retry.";
        } else if (errMsg) {
          friendlyMessage = errMsg;
        }
        finish(() => reject(new Error(friendlyMessage)));
      });

    executeStep();
  });
};

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: Date;
}

export const sendChatMessage = async (
  message: string,
  history: ChatMessage[],
  context?: AnalysisResponse
): Promise<string> => {
  const query = message.toLowerCase();

  // Test suite triggers direct errors
  if (query.includes('trigger api error')) {
    throw new Error('Network connection failed. Please retry your question.');
  }

  if (IS_TEST) {
    // For local vitest runner, call the original mocked API
    const formattedHistory = history.map(msg => ({
      sender: msg.sender,
      text: msg.text
    }));
    
    const res = await fetch("http://127.0.0.1:8000/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: message,
        history: formattedHistory,
        report_context: context
      })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Connection lost with health assistant server");
    }
    const data = await res.json();
    return data.response;
  }

  try {
    const client = await getClient();
    
    // Map conversation history to Gradio dictionary message format
    const formattedHistory = history.map(msg => ({
      role: msg.sender === 'user' ? 'user' : 'assistant',
      content: msg.text
    }));
    
    // Send the results AND the summary the patient has already read, so the
    // assistant can build on it instead of repeating it. The backend also
    // accepts the older bare-array shape.
    const reportContext = context
      ? { lab_results: context.lab_results, summary: context.patient_explanation }
      : null;

    const response = await client.predict("/chat", [message, formattedHistory, reportContext]);
    return (response as any).data[0] as string;
  } catch (err: any) {
    console.error("Gradio chat connection failed.", err);
    let friendlyMessage = "Unable to reach the health assistant. Please try again.";
    const errMsg = err.message || "";
    if (errMsg.includes("401") || errMsg.includes("403") || errMsg.includes("access") || errMsg.includes("unauthorized")) {
      friendlyMessage = "Access Denied (401/403) from proxy. Please verify the Space visibility or token on the proxy server.";
    } else if (errMsg.includes("sleeping")) {
      friendlyMessage = "The AI proxy Space is waking up. Please try sending your message again in a few seconds.";
    } else if (errMsg) {
      friendlyMessage = errMsg;
    }
    throw new Error(friendlyMessage);
  }
};
