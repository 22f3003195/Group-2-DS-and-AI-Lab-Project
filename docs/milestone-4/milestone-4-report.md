*DS\&AI Lab Project \[Term May 2026\]*

**Intelligent Medical Report Analysis System**

 

Milestone \- 4 Report: Model Training, Experimentation, and Evaluation

 

![](./image2.gif)  

Indian Institute of Technology Madras 

 **GROUP: 2**

| Name | Email | GitHub Usernames | Signature |
| :---: | ----- | :---: | ----- |
| Shivendra Patel | 21f2001310@ds.study.iitm.ac.in | shivendra1717 | S.P.  |
| Rajat Srivastava | 22f3003195@ds.study.iitm.ac.in | 22f3003195 | R.S |
| Samta Ranka | 23f1001316@ds.study.iitm.ac.in | 23f1001316 | S.R. |
| Ritwik Trivedi  | 22f1000120@ds.study.iitm.ac.in | ritwiktrivedi | R.T.W |
| Bryan David Robinson | 22f3002277@ds.study.iitm.ac.in | brilo1819 | B.D.R |

# 

# 1\. Dataset Description & Preprocessing

* **Datasets Used:**  
  * **MIMIC-III Clinical Database:** Leveraged full EHR data and clinical lab records for broad-coverage domain alignment and entity distribution.  
  * **MTSamples Dataset:** Utilized medical transcription records to improve entity recognition across various medical specialties and report styles.  
* **Preprocessing Pipeline:**  
  * **OCR Extraction (PaddleOCR):** Raw text extraction from digitized patient lab images/documents into unformatted text strings.  
  * **Table-to-Narrative Cleaning:** Custom pre-processing step converting tabular OCR extractions into standardized string pairs (e.g., wbc 40 10^9/L).  
  * **BIO Entity Alignment:** Automated and manual token-level tagging to annotate sequences with labels: \['O', 'B-TEST', 'I-TEST', 'B-VALUE', 'B-UNIT', 'I-UNIT', 'B-REFERENCE'\].

# 2\. Model Architecture Overview

The overall pipeline operates through a multi-stage architecture:

1. **Perception & Text Extraction:** PaddleOCR parses image pixel inputs and extracts structural text spans.  
2. **Clinical Token Classification (ClinicalBERT):** A fine-tuned ClinicalBERT model acts as a named entity recognition (NER) engine, assigning BIO token tags to extract structured laboratory components (test, value, unit, reference range).  
3. **Structured Data Aggregation:** Extracted entities are normalized into a clean JSON output format.  
4. **Patient Summary Generation (BioMistral 7B):** The structured JSON lab results are formatted as prompts and passed to fine-tuned **BioMistral 7B** to produce patient-friendly clinical explanations and risk assessments.

# 3\. Training Configurations

## 3.1 Information Extraction Engine (ClinicalBERT Token Classifier)

* **Base Model:** ClinicalBERT (medicalai/ClinicalBERT )  
* **Objective / Loss:** Cross-Entropy Loss with padding masking (ignore\_index \= \-100)  
* **Target Tags:** \['O', 'B-TEST', 'I-TEST', 'B-VALUE', 'B-UNIT', 'I-UNIT', 'B-REFERENCE'\]  
* **Metrics:** Token-level and Entity-level Precision, Recall, and Strict F1-score (evaluated via seqeval)  
* **Optimizer:** AdamW (LR \= 0.00002, Weight Decay \= 0.01)  
* **Scheduler:** Linear Warmup over 10% of total steps  
* **Hardware:** CUDA-enabled GPU (Tesla T4/P100 environment)

## 3.2 Patient-Friendly LLM Summarizer (BioMistral 7B)

> * **Base Model:** BioMistral 7B  
> * **Fine-tuning Technique:** *QLoRA 4-bit*  
> * **Loss Function:** *Negative Log Likelihood*  
> * **Optimizer & Schedule:** *AdamW\_torch\_fused , Cosine Annealing*  
> * **Epochs / Steps & Batch Size:** *3 Epochs, train batch size \= 2, Gradient Accumulation \= 4*  
> * **Hardware Used:** *2 \* T4 GPUs* 

## 3.3 Training Setup (ClinicalBERT) 

```py
training_args = TrainingArguments(
    output_dir="./clinicalbert_ner",
    evaluation_strategy="epoch",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=32,
    num_train_epochs=10,
    weight_decay=0.01,
    warmup_ratio=0.1,
    logging_dir='./logs',
    logging_steps=100,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    save_total_limit=3,
    fp16=True,
    dataloader_drop_last=False,
)
```

### 

## 3.4 Hardware Configuration

| Resource | Specification |
| :---- | :---- |
| **GPU** | NVIDIA Tesla T4 |
| **Memory** | 16 GB GPU RAM |
| **CPU** | 4 cores |
| **Training Time** | \-4-6 hours |
| **Framework** | PyTorch / Hugging Face transformers |

## 3.5 Evaluation Metrics Summary

| Metric | Calculation | Purpose |
| :---- | :---- | :---- |
| **Accuracy** | (TP \+ TN) / Total | Overall performance |
| **F1-Score** | 2 \* (P \* R) / (P \+ R) | Entity-level performance |
| **Precision** | TP / (TP \+ FP) | Minimize false positives |
| **Recall** | TP / (TP \+ FN) | Minimize false negatives |
| **Macro F1** | Average per entity | Balanced performance |
| **Weighted F1** | Weighted by support | Class imbalance handling |

# 4\. Fine-Tuning & Experiments

## 4.1 ClinicalBERT NER Fine-Tuning Experiments

ClinicalBERT (`medicalai/ClinicalBERT`) was fine-tuned as a token classification model to extract laboratory entities from medical reports using the BIO tagging scheme. The model was trained on **15138** annotated reports, with **3245** reports each for validation and testing. Five labels were used: **O, B-TEST, I-TEST, B-VALUE, and B-UNIT**.

The model was trained using the **AdamW** optimizer with a learning rate of **2 × 10⁻⁵**, a batch size of **32**, **10 epochs**, a maximum sequence length of **128**, **0.01 weight decay**, and a **linear learning-rate scheduler** with a **10% warm-up ratio**. Training was performed on a **Tesla T4 GPU** using mixed-precision (FP16). To address class imbalance, **weighted cross-entropy loss** with inverse square-root class weighting was employed.

During training, the model converged steadily, with validation loss decreasing from **0.0233** in the first epoch to **0.0031** in the final epoch. The final validation **Entity F1-score** reached **0.99**, while the test set achieved an **accuracy of 0.99**, **weighted F1-score of 0.99**, and **Entity F1-score of 0.9993**. These results demonstrate that ClinicalBERT effectively learned to identify laboratory test names, values, and units from the annotated medical reports.

## 4.2 BioMistral 7B Fine-Tuning Experiments

## **Dataset Construction**

Instruction-tuning pairs were built from the upstream extraction pipeline rather than from raw text. Extracted data from the ClinicalBert model was imported into the notebook and used as the user input. The assistant turn is a patient-facing explanation generated by a large teacher model (nvidia/nemotron-3-ultra-550b-a55b) under a fixed prompt template, making this a knowledge-distillation setup rather than direct human annotation.

The corpus contains **92 examples** sourced from MIMIC-III, split 80/20 with seed=42 into **73 training** and **19 evaluation** examples. Examples were stored in chat format (messages with role / content) and tokenised through the model's chat template with max\_length=1024 and packing disabled.

## **Quantisation and Adapter Setup**

BioMistral-7B was loaded in 4-bit via BitsAndBytes using NF4 quantisation, double quantisation, and a bfloat16 compute dtype, then passed through prepare\_model\_for\_kbit\_training. LoRA adapters were injected into all seven projection matrices of each transformer block: q\_proj, k\_proj, v\_proj, o\_proj, gate\_proj, up\_proj, down\_proj. At the selected rank this yields **20,971,520 trainable parameters out of 7,262,703,616 total, or 0.2888%**, which is what makes 7B fine-tuning viable inside 2 × 16 GB T4 memory.

## **Hyperparameter Search**

Rather than hand-picking adapter settings, we ran an **Optuna** study (TPE sampler, seed=42, MedianPruner, objective \= minimise evaluation loss) over the following space.

| Hyperparameter | Search space |
| :---- | :---: |
| LoRA rank r | {8, 16, 32, 64} |
| alpha\_mult  (α \= r × alpha\_mult) | {1, 2, 4} |
| LoRA dropout | Uniform(0.0, 0.2) |
| Learning rate | Log-uniform(1e-5, 5e-4) |

 

Each trial trained for a capped budget of max\_steps=30 (approximately 3 epochs over the 73-example training split, as reported in the logs) with per-device batch size 2, gradient accumulation 4, cosine schedule, 3% warmup, bf16, and loss\_type="nll". Everything except the four searched parameters was held fixed so that trials remained comparable. Between trials the adapter was stripped with unload() and CUDA memory released, so each trial started from the same quantised base weights without reloading from disk.

*Table 4.2.1 — Full Optuna trial results (all 8 trials; TPE sampler, seed 42).*

| Trial | r | α | Dropout | Learning rate | Train loss | Eval loss | Token acc. | Entropy |
| :---- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | 16 | 16 | 0.1732 | 1.050e-4 | 0.8808 | 0.7697 | 0.7854 | 0.7241 |
| 1 | 32 | 32 | 0.0608 | 7.790e-5 | 0.8047 | 0.7427 | 0.7935 | 0.6844 |
| 2 | 32 | 128 | 0.1570 | 2.184e-5 | 0.8324 | 0.7847 | 0.7852 | 0.7198 |
| 3 | 64 | 256 | 0.1931 | 2.363e-4 | 0.5425 | 0.7403 | 0.8033 | 0.4112 |
| 4 | 32 | 64 | 0.1819 | 2.752e-5 | 0.9491 | 0.8515 | 0.7680 | 0.8194 |
| **5 (best)** | **8** | **16** | **0.18790** | **3.313e-4** | **0.6319** | **0.6906** | **0.8075** | **0.5387** |
| 6 | 16 | 64 | 0.0543 | 2.559e-4 | 0.5168 | 0.7131 | 0.8107 | 0.4594 |
| 7 | 32 | 128 | 0.1544 | 2.176e-5 | 0.8331 | 0.7851 | 0.7855 | 0.7201 |

 

*Trial 5 was selected as the final configuration, achieving the lowest evaluation loss of the study,* **0.6906***. The complete study ran from 12:32 to 16:50 (approximately 4 hours 17 minutes wall-clock across all eight trials).*

**Selected configuration (Trial 5):** r=8, lora\_alpha=16, lora\_dropout=0.18790, learning\_rate=3.3135e-4, eval loss 0.6906.

## **Observations from the Search**

•     **Capacity was not the limiting factor.** The winning configuration used the smallest rank in the search, r=8, yet reached the lowest evaluation loss (0.6906). The largest adapter, r=64 in Trial 3, drove train loss down to 0.5425 but did not generalise best, confirming that on 73 examples the task is not adapter-capacity-bound.

•     **Learning rate was the dominant hyperparameter.** Ordering the trials by learning rate reproduces the ordering by evaluation loss almost exactly. The three trials with rates near 2.2e-5 (Trials 2, 4 and 7\) sit at the bottom with eval loss between 0.785 and 0.852, while the four highest-rate trials (1, 3, 6 and 5\) occupy the top, with the winner at 3.31e-4. Within the 30-step budget the search consistently rewarded faster movement.

•     **The best configuration generalised rather than memorised.** Trials 3 and 6 pushed train loss lowest (0.54 and 0.52) but showed a train-to-eval gap of roughly 0.20, a mild overfitting signature. Trial 5 sat at a moderate train loss of 0.63 with the smallest gap (0.06) and the best eval loss, indicating the winning setup traded a little training fit for markedly better held-out behaviour.

•     **Model confidence tracked performance.** Evaluation entropy fell from around 0.72 to 0.82 in the underfit low-rate trials down to 0.41 to 0.54 in the top trials, so the stronger configurations also produced more decisive next-token distributions rather than hedged ones.

## **Key Findings**

**What worked well.**

QLoRA plus adapter reuse across trials made an 8-trial architecture search feasible on free-tier hardware, which would have been impossible with full fine-tuning of a 7B model. The selected configuration reached token-level accuracy of 0.81 on the eval split with a loss of 0.69, indicating the model learned the target output structure (one bullet per test, followed by a recommendation block) quickly.

**What did not work as expected, and bottlenecks.**

•     **Dataset size is the binding constraint.** 92 examples, of which 73 are trainable, is well below the 200 to 500 reviewed examples the pipeline design called for. With 19 eval examples, a single poor generation shifts the metrics materially, so all reported figures carry wide uncertainty.

•     **Compute wall-clock.** Each trial took roughly 31 minutes (train runtimes of 1844 to 1907 seconds), so the full 8-trial study ran about 4 hours 17 minutes (12:32 to 16:50) before the dedicated training run could begin. That final 3-epoch run was interrupted before completion for this reason.

•     **bfloat16 on Tesla T4.** T4 is a Turing-class GPU without native bf16 tensor cores, so the bf16 compute path is emulated and slow. This is the primary driver of the approximately 63 seconds per optimization step observed.

> 

# 5\. Regularization & Training Stability

## 5.1 Techniques Used

| Technique | Description | Impact |
| :---- | :---- | :---- |
| **Optimizer (AdamW)** | Weight decay-decoupled adaptive optimizer (lr=2e-5, weight\_decay=0.01) | Prevents overfitting |
| **Weight Decay** | L2 regularization (0.01) | Improves generalization |
| **Warmup Steps** | Linear warmup for first 10% of steps | Stabilizes early training |
| **Gradient Clipping** | Max norm \= 1.0 | Prevents gradient explosion |
| **Mixed Precision (FP16)** | 16-bit floating point | Faster training, less memory |
| **Dropout** | Randomly zeroes activations (p=0.1) in attention and hidden layers | Reduces overfitting |
| **Best Model Selection** | Restores weights from the epoch with the lowest validation loss | Ensures best validation performance  |

## 5.2 Training & Loss Plots

# 6\. Quantitative & Qualitative Results

## 6.1 Quantitative Evaluation (ClinicalBERT) 

* **ClinicalBERT NER Performance:**   
  * Overall Token Accuracy: 99.97%  
  * Entity-Level Macro F1-Score: 99.96%  
  * Overall Weighted F1-Score: 99.97%  
  * Test Loss: 0.00239

## 6.2 BioMistral 7B Quantitative Evaluation

### Values below are from the selected configuration (Trial 5\) evaluated on the 19-example held-out split. Each search trial ran to a 3-epoch-equivalent budget of 30 steps, so these figures are representative of the intended final model, and are to be confirmed against the completed dedicated training run.

| Metric | Selected model (Trial 5\) | Notes |
| :---- | :---: | :---: |
| Eval loss (NLL) | 0.6906 | Lowest of the 8 trials |
| Perplexity | 1.99 | exp(0.6906) |
| Eval mean token accuracy | 0.8075 | Next-token agreement with reference |
| Eval entropy | 0.5387 | Lower indicates more confident predictions |
| Train loss | 0.6319 | Train-to-eval gap of 0.06 (good generalisation) |
| Trainable parameters | 20,971,520 (0.2888%) | LoRA adapter only; base weights frozen |
| Evaluation set size | 19 examples | Small; treat figures as indicative |

## 6.3 Qualitative Evaluation

| Observation | Details |
| :---- | :---- |
| **Multi-word tests** | Correctly parses complex clinical terms like "White Blood Cells" and "Alkaline Phosphatase".  |
| **Units** | Near-perfect detection across diverse units (g/dL, 10^9/L, mEq/L, %).  |
| **Values** | Excellent boundary detection for floating point and integer test results.  |
| **Reference ranges** | Lower recall on reference ranges due to formatting variations across different hospital labs.  |
| **Context understanding** | Successfully resolves shorthand variations (e.g., Hgb vs. Hemoglobin, WBC vs. White Blood Count).  |
| **OCR Mapping**  | Effectively aligns raw OCR outputs into clean JSON key-value pairs.  |

# 7\. Sample Output from End-to-End Pipeline

## 7.1 Sample Input Text (Post-OCR Narrative)

```
LABORATORY RESULTS:
Hemoglobin: 14.2 g/dL
Glucose: 98 mg/dL
Creatinine: 1.1 mg/dL
Potassium: 4.0 mEq/L
Sodium: 140 mEq/L
WBC Count: 8.5 K/uL
Platelets: 250 K/uL
```

### 

## 7.2 Token-Level Predictions

```
Token        →  Predicted Label
─────────────────────────────────
LABORATORY   →  O
RESULTS      →  O
Hemoglobin   →  B-TEST
:            →  O
14.2         →  B-VALUE
g/dL         →  B-UNIT
Glucose      →  B-TEST
:            →  O
98           →  B-VALUE
mg/dL        →  B-UNIT
Creatinine   →  B-TEST
:            →  O
1.1          →  B-VALUE
mg/dL        →  B-UNIT
...
```

## 7.3 Structured Output

```json
[
  {
    "test": "Hemoglobin",
    "value": "14.2",
    "unit": "g/dL",
    "status": "NORMAL",
    "reference": "13.0-17.0"
  },
  {
    "test": "Glucose",
    "value": "98",
    "unit": "mg/dL",
    "status": "NORMAL",
    "reference": "70-100"
  },
  {
    "test": "Creatinine",
    "value": "1.1",
    "unit": "mg/dL",
    "status": "NORMAL",
    "reference": "0.6-1.3"
  }
]
```

## 

## 7.4 Generated Patient Insights (BioMistral 7B Output)

The generation harness for this section is implemented in Section 11 of the training notebook: it selects a held-out example (eval\_dataset\[5\]), applies the chat template, and generates greedily with max\_new\_tokens=1024, printing the prompt, the fine-tuned model output, and the reference side by side.

## **Input Format**

For continuity with Section 7.3, note that training prompts are raw JSON arrays carrying a status field, as shown below:

 \[{"test": "Bicarbonate", "value": 31.0, "unit": "mEq/L", "test\_name": "Bicarbonate", "status": "HIGH"}, {"test": "Lymphocytes", "value": 46.0, "unit": "mg/dL", "test\_name": "Lymphocytes", "status": "HIGH"}\]  
 

## **Expected Output Format (Reference Target)**

\- **Bicarbonate (31.0 mEq/L, HIGH):** Bicarbonate helps balance your blood's acid level. A high level suggests your blood may be too alkaline (not acidic enough), which can happen with certain kidney or metabolic conditions. It can also occur with prolonged vomiting or diarrhea.

\- **Lymphocytes (46.0 mg/dL, HIGH):** Lymphocytes are a type of white blood cell that help your body fight infections and diseases. A high count is called lymphocytosis and can be caused by recent viral infections, stress, certain medications, or an underlying immune condition.

**Recommendation:** Discuss both results with your doctor. They may want to repeat the bicarbonate test (fasting or non-fasting) to check your body's acid-base balance. They may also review your medications and recent illnesses to determine the cause of the lymphocytosis.

 

# 8\. Artifacts Generated

## 8.1 Model Files

| File | Size | Description |
| :---- | :---- | :---- |
| model.safetensors | \-514 MB | Trained model weights (SafeTensors binary format) |
| config.json | \-847 B | Model architecture configuration |
| label\_mapping.json | \-302 B | Label-to-ID mappings (0: O, 1: B-TEST, 2: I-TEST, 3: B-VALUE, 4: B-UNIT) |
| text\_classification\_report.txt | \-488 B | Saved classification report summary |
| tokenizer.json | \-2.78 MB | Tokenizer vocabulary and merged rules configuration |
| tokenizer\_config.json | \-382 B | Tokenizer hyperparameters and special token settings |
| training\_args.bin | \-5.14 KB | Binary serialized Hugging Face training arguments |
| training\_configuration.json | \-1.77 KB | Detailed JSON configuration of training hyperparameters |

## 8.2 Training Artifacts

| Artifact | Path | Description |
| :---- | :---- | :---- |
| Training logs | ./logs/ | TensorBoard training and evaluation event logs |
| Checkpoints | ./checkpoint-\*/ | Checkpoint state folders containing intermediate weights |
| Metrics | ./eval\_results.json | Evaluation metrics |
| Predictions | ./predictions.jsonl | Model predictions |

## 8.3 Data Artifacts

| Artifact | Path | Description |
| :---- | :---- | :---- |
| Training data | train\_reports.jsonl |  train annotated samples |
| Validation data | val\_reports.jsonl |  validation annotated samples |
| Test data | test\_reports.jsonl |  test annotated samples |
