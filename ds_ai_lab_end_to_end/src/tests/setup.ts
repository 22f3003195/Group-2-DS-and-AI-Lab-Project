import '@testing-library/jest-dom';
import { vi } from 'vitest';

console.log('--- TEST SETUP RUNNING ---');

const matchMediaMock = (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  configurable: true,
  value: matchMediaMock,
});

Object.defineProperty(globalThis, 'matchMedia', {
  writable: true,
  configurable: true,
  value: matchMediaMock,
});

const mockResponseData = {
  report: {
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
    }
  },
  summary: `## Your Results Overview

We analyzed your medical report and extracted **6 key test results**. Overall, **3 values are outside the normal reference ranges** (Hemoglobin, Platelets, and Total Cholesterol). The rest of your numbers, including White Blood Cell count and TSH, look healthy and normal.`
};

const mockChatResponse = {
  response: "Your hemoglobin level is **10.2 g/dL**, which is below the normal range of **12.0–16.0 g/dL**. Hemoglobin carries oxygen throughout your body, and lower levels can cause mild fatigue."
};

globalThis.fetch = vi.fn((url: string, options?: any) => {
  if (url.includes('/api/reports/analyze')) {
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockResponseData),
    });
  }
  if (url.includes('/api/chat')) {
    let msg = "";
    if (options && options.body) {
      try {
        const bodyObj = JSON.parse(options.body);
        msg = (bodyObj.message || "").toLowerCase();
      } catch (e) {}
    }
    
    let responseText = "Your hemoglobin level is **10.2 g/dL**, which is below the normal range of **12.0–16.0 g/dL**. Hemoglobin carries oxygen throughout your body, and lower levels can cause mild fatigue.";
    
    if (msg.includes('platelet') || msg.includes('clot')) {
      responseText = "Your platelet count is **520 10^9/L**, which is slightly higher than the normal limit of **450 10^9/L**. Platelets are key blood clotting cells. Mild elevations can be reactive to inflammation or iron changes.";
    }
    
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ response: responseText }),
    });
  }
  return Promise.reject(new Error(`Unhandled fetch mock for URL: ${url}`));
}) as any;
