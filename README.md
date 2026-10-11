# Accident Pattern Discovery Using Apriori

## Overview

Accident Pattern Discovery analyzes road accident records to identify frequently occurring combinations of accident-related factors using the Apriori association rule mining algorithm.

The project explores relationships among recorded attributes such as accident severity, traffic density, traffic signals, road type, weather, and time of day. An interactive dashboard lets users review dataset statistics, adjust minimum support and confidence thresholds, visualize accident data, and examine generated association rules.

The goal is to support exploratory road safety analysis of historical records. Discovered patterns describe associations in the dataset; they do not establish causation or real-world accident risk.

## Objectives

- Analyze the distribution of accident severity and other recorded factors.
- Identify frequent itemsets using the Apriori algorithm.
- Generate association rules between accident-related attributes.
- Evaluate rules using support, confidence, and lift.
- Provide an interactive dashboard for exploring results at different thresholds.
- Present findings clearly while distinguishing association from causation.

## Key Features

- **Dataset overview:** Displays the number of records, attributes, and other available statistics.
- **Accident severity analysis:** Visualizes the distribution of recorded severity categories.
- **Frequent factor analysis:** Highlights frequently occurring categorical values in the dataset.
- **Apriori pattern mining:** Finds frequent itemsets and generates rules using user-selected thresholds.
- **Interactive visualizations:** Explores dataset frequencies and compares rule confidence and lift.
- **Association-rule explorer:** Shows antecedents, consequents, support, confidence, lift, and plain-language interpretations.
- **Configurable analysis:** Lets users adjust minimum support and minimum confidence.

## How It Works

1. **Data preprocessing:** Accident records are loaded and converted into transactions suitable for association rule mining.
2. **Frequent itemset generation:** Apriori identifies item combinations that meet the minimum support threshold.
3. **Association rule generation:** Rules are generated from frequent itemsets and filtered using the minimum confidence threshold.
4. **Rule evaluation:** Support, confidence, and lift describe the frequency and strength of observed associations.
5. **Visualization:** The frontend displays dataset statistics, charts, and discovered rules.

## Understanding the Metrics

| Metric | Description |
|---|---|
| **Support** | The proportion of all transactions containing the items in a rule. |
| **Confidence** | The proportion of transactions containing the antecedent that also contain the consequent. |
| **Lift** | Compares the observed association with the frequency expected if the antecedent and consequent were independent. A lift greater than 1 indicates a positive association under the standard definition; a lift close to 1 indicates little difference from the independence baseline; a lift below 1 indicates a negative association. |

## Technology Stack

- **Frontend:** React, Vite, Tailwind CSS, Plotly.js
- **Backend:** Python, Flask
- **Data processing:** pandas
- **Data mining:** Apriori association rule mining
- **Communication:** REST API

## Project Structure

```text
accident_pattern_discovery/
├── backend/
│   ├── app.py
│   ├── apriori.py
│   ├── preprocessing.py
│   ├── data/
│   └── tests/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
└── README.md
```

## Getting Started

### Prerequisites

- Python 3
- Node.js and npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Methika2005/accident_pattern_discovery.git
cd accident_pattern_discovery
```

### 2. Set up the backend

From the project root, create and activate a virtual environment.

**Windows Command Prompt:**

```bat
python -m venv backend\.venv
backend\.venv\Scripts\activate
```

Install the backend dependencies according to the project's dependency file. If no dependency file is available, install the packages required by the backend.

Start the Flask server using the project's existing entry point:

```bash
python backend\app.py
```

### 3. Set up the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite in your browser.

### 4. Explore the analysis

1. Open the dashboard.
2. Review the dataset overview and visualizations.
3. Enter the desired minimum support and minimum confidence values.
4. Run the analysis.
5. Explore the generated association rules and their metrics.
6. Compare results obtained using different thresholds.

## Interpreting the Results

Discovered rules describe combinations of attributes that occur together in the analyzed records. For example, a rule may show that a particular traffic condition frequently co-occurs with a certain time of day or weather condition.

These patterns may be useful for further investigation. However, association rules do not establish causation, and frequently occurring attributes do not necessarily indicate increased accident risk.

## Limitations

- Results depend on the quality, completeness, and representativeness of the dataset.
- Association rules identify co-occurrence, not causal relationships.
- The selected support and confidence thresholds affect which patterns are discovered.
- Frequent patterns alone cannot establish real-world accident risk or predict future accidents.
- Findings should be interpreted in the context of the available records and attributes.

## Future Scope

- Compare patterns across accident severity categories.
- Add filters for weather conditions, road types, times, and other attributes.
- Improve rule ranking and filtering to help users focus on relevant patterns.
- Explore additional data mining methods and evaluate their usefulness for road safety research.

## Contributors

Developed as a collaborative academic project on road accident pattern discovery using association rule mining.

## License

Add the applicable license information here.