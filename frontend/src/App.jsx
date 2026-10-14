
import { useCallback, useEffect, useMemo, useState } from "react";
import Plot from "react-plotly.js";
import {
  Activity,
  BarChart3,
  CarFront,
  CheckCircle2,
  CircleAlert,
  Database,
  Gauge,
  GitBranch,
  LoaderCircle,
  Play,
  RefreshCw,
  ShieldAlert,
  SlidersHorizontal,
  TrendingUp,
  X,
} from "lucide-react";

import { checkHealth, getDatasetStats, minePatterns } from "./services/api";
import "./App.css";

const chartLayout = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#cbd5e1", family: "Inter, Arial, sans-serif", size: 12 },
  margin: { l: 48, r: 20, t: 20, b: 48 },
  xaxis: {
    gridcolor: "rgba(148,163,184,0.14)",
    zerolinecolor: "rgba(148,163,184,0.24)",
  },
  yaxis: {
    gridcolor: "rgba(148,163,184,0.14)",
    zerolinecolor: "rgba(148,163,184,0.24)",
  },
  legend: { orientation: "h", y: -0.2 },
  autosize: true,
};

const chartConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

const conditionAttributeLabels = [
  { key: "weather", label: "Weather" },
  { key: "traffic_density", label: "Traffic density" },
  { key: "road_type", label: "Road type" },
  { key: "traffic_signal", label: "Traffic signal status" },
  { key: "time_of_day", label: "Time of day" },
];

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "—";

  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);

  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(number);
}

function formatPercentage(value) {
  if (value === null || value === undefined || value === "") return "—";

  if (typeof value === "string" && value.includes("%")) {
    return `${value.replace("%", "").trim()}%`;
  }

  const number = Number(value);
  if (!Number.isFinite(number)) return "—";

  return `${(number <= 1 ? number * 100 : number).toFixed(1)}%`;
}

function parseMetric(value) {
  if (value === null || value === undefined || value === "") return NaN;

  const number = Number(String(value).replace("%", "").trim());
  return Number.isFinite(number) ? number : NaN;
}

function formatItemLabel(value) {
  return String(value)
    .split("=")
    .map((part) =>
      part
        .replaceAll("_", " ")
        .trim()
        .replace(/\b\w/g, (character) => character.toUpperCase())
    )
    .join(": ");
}

function getFirstValue(object, keys, fallback = null) {
  if (!object) return fallback;

  for (const key of keys) {
    if (object[key] !== undefined && object[key] !== null) {
      return object[key];
    }
  }

  return fallback;
}

function getFrequencyEntries(stats) {
  const frequencies = stats?.item_frequencies;

  if (!frequencies) return [];

  if (Array.isArray(frequencies)) {
    return frequencies
      .map((item) => {
        if (!item || typeof item !== "object") return null;

        const rawCount =
          item.count ?? item.frequency ?? item.support_count;
        return {
          label: String(
            item.item ?? item.name ?? item.label ?? item.attribute_value ?? ""
          ),
          count:
            typeof rawCount === "number" ? rawCount : NaN,
          support: item.support,
        };
      })
      .filter(
        (item) =>
          item !== null &&
          item.label &&
          Number.isFinite(item.count) &&
          Number.isInteger(item.count) &&
          item.count >= 0
      );
  }

  if (typeof frequencies === "object") {
    return Object.entries(frequencies)
      .map(([label, value]) => {
        const rawCount =
          typeof value === "object" && value !== null
            ? value.count ?? value.frequency ?? value.support_count
            : value;
        return {
          label,
          count:
            typeof rawCount === "number" ? rawCount : NaN,
          support:
            typeof value === "object" && value !== null
              ? value.support
              : null,
        };
      })
      .filter(
        (item) =>
          Number.isFinite(item.count) &&
          Number.isInteger(item.count) &&
          item.count >= 0
      );
  }

  return [];
}

function getConditionAttributes(stats) {
  const totalRecords = Number(stats?.transaction_count);
  const frequencies = getFrequencyEntries(stats).filter(
    (item) =>
      Number.isFinite(totalRecords) &&
      Number.isInteger(totalRecords) &&
      totalRecords > 0 &&
      item.count <= totalRecords
  );
  const availableAttributes = conditionAttributeLabels
    .map((attribute) => {
      const expectedValues = stats?.attribute_values?.[attribute.key];
      const entries = frequencies
        .flatMap((item) => {
          const separator = item.label.indexOf("=");
          if (separator < 0) return [];

          const key = item.label.slice(0, separator).trim().toLowerCase();
          const value = item.label.slice(separator + 1).trim();
          if (key !== attribute.key || !value) return [];

          return [{ value, count: item.count }];
        })
        .sort(
          (a, b) =>
            b.count - a.count || a.value.localeCompare(b.value)
        );
      const expectedValueSet = new Set(
        Array.isArray(expectedValues) ? expectedValues.map(String) : []
      );
      const actualValueSet = new Set(entries.map((item) => item.value));

      return {
        ...attribute,
        entries,
        complete:
          expectedValueSet.size > 0 &&
          expectedValueSet.size === entries.length &&
          actualValueSet.size === entries.length &&
          entries.every((item) => expectedValueSet.has(item.value)),
      };
    })
    .filter(
      (attribute) =>
        attribute.entries.length > 0 ||
        (Array.isArray(stats?.attribute_values?.[attribute.key]) &&
          stats.attribute_values[attribute.key].length > 0)
    );

  return availableAttributes;
}

function getSeverityEntries(stats) {
  return getFrequencyEntries(stats)
    .map((item) => {
      const match = item.label
        .trim()
        .match(/^(?:accident_)?severity\s*=\s*(.+)$/i);
      return match
        ? { ...item, label: formatItemLabel(match[1]) }
        : null;
    })
    .filter(Boolean);
}

function normalizeRule(rule, index) {
  const antecedent = getFirstValue(rule, [
    "antecedents",
    "antecedent",
    "lhs",
    "left",
    "condition",
    "if",
  ]);

  const consequent = getFirstValue(rule, [
    "consequents",
    "consequent",
    "rhs",
    "right",
    "result",
    "then",
  ]);

  const toText = (value) => {
    if (Array.isArray(value)) return value.map(String).join(", ");
    if (value && typeof value === "object") return JSON.stringify(value);
    return value == null ? "" : String(value);
  };

  const rawSupport = parseMetric(
    getFirstValue(rule, ["support", "support_pct", "support_percentage"])
  );
  const rawConfidence = parseMetric(
    getFirstValue(rule, ["confidence", "confidence_pct"])
  );
  const rawLift = parseMetric(getFirstValue(rule, ["lift", "lift_ratio"]));

  return {
    id: index + 1,
    condition:
      (Array.isArray(antecedent)
        ? antecedent.map(formatItemLabel).join(", ")
        : formatItemLabel(toText(antecedent))) || "—",
    result:
      (Array.isArray(consequent)
        ? consequent.map(formatItemLabel).join(", ")
        : formatItemLabel(toText(consequent))) || "—",
    support: formatPercentage(Number.isFinite(rawSupport) ? rawSupport : null),
    confidence: formatPercentage(
      Number.isFinite(rawConfidence) ? rawConfidence : null
    ),
    lift: formatNumber(Number.isFinite(rawLift) ? rawLift : null),
    rawSupport,
    rawConfidence,
    rawLift,
  };
}

function KeyInference({ takeaway, evidence, caveat }) {
  return (
    <div className="key-inference mt-4 px-4 py-3">
      <p className="text-sm font-semibold text-slate-900">
        {takeaway || "Key inference"}
      </p>
      <p className="mt-1 text-sm leading-6 text-slate-700">
        {evidence}
      </p>
      {caveat && (
        <p className="mt-1 text-xs leading-5 text-slate-500">{caveat}</p>
      )}
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, description, accent }) {
  return (
    <div className="metric-card rounded-2xl border border-slate-800 bg-slate-900/70 p-5 transition hover:border-slate-700">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-white">
            {value}
          </p>
        </div>
        <div className={`metric-icon rounded-xl p-3 ${accent}`}>
          <Icon size={21} />
        </div>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{description}</p>
    </div>
  );
}

function Panel({ title, subtitle, icon: Icon, children }) {
  return (
    <section className="panel-surface min-w-0 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 sm:p-7">
      <div className="mb-5 flex items-start gap-3">
        <div className="panel-icon rounded-lg bg-slate-800 p-2 text-cyan-300">
          <Icon size={18} />
        </div>
        <div className="min-w-0">
          <h2 className="font-semibold text-white">{title}</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function EmptyChart({ message }) {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-xl border border-dashed border-slate-700 px-5 text-center">
      <div>
        <BarChart3 className="mx-auto mb-3 text-slate-600" size={28} />
        <p className="text-sm text-slate-300">{message}</p>
        <p className="mt-2 text-xs text-slate-500">
          No sample or estimated values are used.
        </p>
      </div>
    </div>
  );
}

function App() {
  const [activePage, setActivePage] = useState("Overview");

  // Input fields store strings so they can be temporarily empty while editing.
  const [support, setSupport] = useState("0.05");
  const [confidence, setConfidence] = useState("0.5");

  const [stats, setStats] = useState(null);
  const [rules, setRules] = useState([]);
  const [frequentItemsetCount, setFrequentItemsetCount] = useState(null);
  const [apiHealth, setApiHealth] = useState({
    status: "checking",
    message: "Checking backend connection...",
  });

  const [loadingStats, setLoadingStats] = useState(true);
  const [loading, setLoading] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState("idle");
  const [analysisParameters, setAnalysisParameters] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lastRun, setLastRun] = useState(null);

  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    setError("");
    setStats(null);

    try {
      const data = await getDatasetStats();
      setStats(data?.stats ?? data?.data ?? data);
    } catch (err) {
      setStats(null);
      setError(err.message || "Could not load dataset statistics.");
    } finally {
      setLoadingStats(false);
    }
  }, []);

  const loadApiHealth = useCallback(async () => {
    setApiHealth({
      status: "checking",
      message: "Checking backend connection...",
    });

    try {
      const health = await checkHealth();
      if (health?.status !== "ok" || health?.dataset_loaded !== true) {
        setApiHealth({
          status: "unavailable",
          message: health?.error || "The dataset is not available.",
        });
        return;
      }

      setApiHealth({
        status: "ready",
        message: "Flask API connected and dataset loaded.",
      });
    } catch (err) {
      setApiHealth({
        status: "unavailable",
        message: err.message || "Could not connect to the Flask API.",
      });
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      loadStats();
      loadApiHealth();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [loadApiHealth, loadStats]);

  const refreshDashboard = useCallback(async () => {
    await Promise.all([loadStats(), loadApiHealth()]);
  }, [loadApiHealth, loadStats]);

  async function handleRun() {
    setError("");
    setNotice("");

    const supportValue = Number(support);
    const confidenceValue = Number(confidence);

    if (
      support.trim() === "" ||
      !Number.isFinite(supportValue) ||
      supportValue < 0.01 ||
      supportValue > 1
    ) {
      setError("Minimum support must be between 0.01 and 1.");
      return;
    }

    if (
      confidence.trim() === "" ||
      !Number.isFinite(confidenceValue) ||
      confidenceValue < 0.01 ||
      confidenceValue > 1
    ) {
      setError("Minimum confidence must be between 0.01 and 1.");
      return;
    }

    setRules([]);
    setFrequentItemsetCount(null);
    setLastRun(null);
    setAnalysisParameters(null);
    setAnalysisStatus("loading");
    setLoading(true);

    try {
      const result = await minePatterns({
        min_support: supportValue,
        min_confidence: confidenceValue,
        max_k: 4,
      });

      const returnedRules =
        result?.rules ??
        result?.association_rules ??
        result?.results?.rules ??
        result?.data?.rules ??
        [];

      if (!Array.isArray(returnedRules)) {
        throw new Error(
          "The API returned rules in an unexpected format. Check its response structure."
        );
      }

      setRules(returnedRules.map(normalizeRule));

      setFrequentItemsetCount(
        getFirstValue(result, [
          "frequent_itemset_count",
          "frequent_itemsets_count",
          "num_frequent_itemsets",
          "itemset_count",
        ]) ??
          getFirstValue(result?.metrics, [
            "frequent_itemset_count",
            "frequent_itemsets_count",
            "num_frequent_itemsets",
            "itemset_count",
          ]) ??
          getFirstValue(result?.results, [
            "frequent_itemset_count",
            "frequent_itemsets_count",
            "num_frequent_itemsets",
            "itemset_count",
          ]) ??
          null
      );

      setLastRun(new Date());
      setAnalysisParameters({
        support: supportValue,
        confidence: confidenceValue,
      });
      setAnalysisStatus(returnedRules.length > 0 ? "success" : "empty");
      setNotice(
        returnedRules.length > 0
          ? `Analysis complete. ${returnedRules.length} association rule(s) returned.`
          : "Analysis complete. No association rules met the selected thresholds."
      );
    } catch (err) {
      setAnalysisStatus("error");
      setError(err.message || "Could not run association rule mining.");
    } finally {
      setLoading(false);
    }
  }

  const severityEntries = useMemo(
    () => getSeverityEntries(stats),
    [stats]
  );

  const conditionAttributes = useMemo(
    () => getConditionAttributes(stats),
    [stats]
  );
  const conditionRecordCount = getFirstValue(stats, ["transaction_count"]);
  const totalConditionRecords = parseMetric(conditionRecordCount);
  const conditionSummaries = useMemo(
    () =>
      conditionAttributeLabels
        .filter(
          (attribute) =>
            (Array.isArray(stats?.attributes_used) &&
              stats.attributes_used.includes(attribute.key)) ||
            Object.hasOwn(stats?.attribute_values ?? {}, attribute.key)
        )
        .map((attribute) => {
          const condition = conditionAttributes.find(
            (item) => item.key === attribute.key
          );
          const rawMissingCount =
            stats?.missing_values_per_attribute?.[attribute.key];
          const missingCount =
            typeof rawMissingCount === "number" &&
            Number.isInteger(rawMissingCount) &&
            rawMissingCount >= 0 &&
            Number.isFinite(totalConditionRecords) &&
            rawMissingCount <= totalConditionRecords
              ? rawMissingCount
              : null;

          return {
            ...attribute,
            winner:
              condition?.complete && condition.entries.length > 0
                ? condition.entries[0]
                : null,
            missingCount,
          };
        }),
    [conditionAttributes, stats, totalConditionRecords]
  );
  const commonConditionEntries = useMemo(
    () =>
      conditionSummaries
        .filter((attribute) => attribute.winner)
        .map((attribute) => ({
          ...attribute,
          percentage:
            Number.isFinite(totalConditionRecords) &&
            totalConditionRecords > 0
              ? (attribute.winner.count / totalConditionRecords) * 100
              : null,
        }))
        .sort(
          (a, b) =>
            b.winner.count - a.winner.count ||
            a.label.localeCompare(b.label)
        ),
    [conditionSummaries, totalConditionRecords]
  );
  const unavailableConditionLabels = conditionSummaries
    .filter((attribute) => !attribute.winner)
    .map((attribute) => attribute.label);

  const rulePoints = useMemo(
    () =>
      rules
        .map((rule) => ({
          ...rule,
          confidenceValue:
            Number.isFinite(rule.rawConfidence) && rule.rawConfidence >= 0
              ? rule.rawConfidence <= 1
                ? rule.rawConfidence * 100
                : rule.rawConfidence
              : Number(String(rule.confidence).replace("%", "")),
          liftValue: rule.rawLift,
        }))
        .filter(
          (rule) =>
            Number.isFinite(rule.confidenceValue) &&
            Number.isFinite(rule.liftValue)
        ),
    [rules]
  );

  const transactionCount = getFirstValue(stats, [
    "transaction_count",
    "total_transactions",
    "num_transactions",
    "total_records",
    "total_rows",
    "rows",
  ]);

  const severityInference = useMemo(() => {
    if (severityEntries.length === 0) return null;

    const mostFrequent = severityEntries.reduce((highest, item) =>
      item.count > highest.count ? item : highest
    );
    const total = parseMetric(transactionCount);
    const support = parseMetric(mostFrequent.support);
    const percentage =
      Number.isFinite(total) && total > 0
        ? (mostFrequent.count / total) * 100
        : Number.isFinite(support)
          ? (support <= 1 ? support * 100 : support)
          : null;
    const evidence =
      Number.isFinite(total) && total > 0
        ? `${formatNumber(mostFrequent.count)} of ${formatNumber(total)} records (${percentage.toFixed(1)}%) were classified as ${mostFrequent.label.toLowerCase()}.`
        : Number.isFinite(percentage)
          ? `${formatNumber(mostFrequent.count)} records (${percentage.toFixed(1)}% of records) were classified as ${mostFrequent.label.toLowerCase()}.`
          : `${formatNumber(mostFrequent.count)} records were classified as ${mostFrequent.label.toLowerCase()}.`;

    return {
      takeaway: `Most recorded accidents were ${mostFrequent.label.toLowerCase()}.`,
      evidence,
      caveat: "This describes the dataset distribution, not real-world accident risk.",
    };
  }, [severityEntries, transactionCount]);

  const conditionInference = useMemo(() => {
    if (commonConditionEntries.length === 0) return null;
    const mostFrequent = commonConditionEntries[0];
    return {
      takeaway: `${mostFrequent.label}: ${formatItemLabel(mostFrequent.winner.value)} was the most common recorded category.`,
      evidence: commonConditionEntries
        .map(
          (attribute) =>
            `${attribute.label}: ${formatItemLabel(attribute.winner.value)} (${formatNumber(attribute.winner.count)} records, ${attribute.percentage.toFixed(1)}% of analyzed records)`
        )
        .join(". "),
      caveat: "This is a distribution among recorded accidents, not evidence of cause or accident probability.",
    };
  }, [commonConditionEntries]);

  const associationInference = useMemo(() => {
    if (rules.length === 0 || rulePoints.length === 0) return null;

    const strongestRule = rulePoints.reduce((strongest, rule) =>
      rule.liftValue > strongest.liftValue ? rule : strongest
    );

    return {
      takeaway: "This combination is worth investigating.",
      evidence: `In records containing ${strongestRule.condition}, ${strongestRule.result} appeared in ${formatPercentage(strongestRule.confidenceValue / 100)} of cases (confidence). Support was ${strongestRule.support} and lift was ${strongestRule.lift}.`,
    };
  }, [rulePoints, rules.length]);

  const attributesUsed = getFirstValue(stats, [
    "attributes_used",
    "num_attributes",
    "attribute_count",
    "total_attributes",
  ]);

  const droppedRows = getFirstValue(stats, [
    "dropped_rows",
    "rows_dropped",
    "dropped_records",
  ]);

  const attributesExcluded = getFirstValue(stats, [
    "attributes_excluded",
    "excluded_attributes",
  ]);

  const attributeValues = getFirstValue(stats, [
    "attribute_values",
    "unique_values",
    "categorical_values",
  ]);

  const attributeCount =
    Array.isArray(attributesUsed) ||
    (attributesUsed && typeof attributesUsed === "object")
      ? Object.keys(attributesUsed).length
      : attributesUsed;

  const excludedCount =
    Array.isArray(attributesExcluded) ||
    (attributesExcluded && typeof attributesExcluded === "object")
      ? Object.keys(attributesExcluded).length
      : attributesExcluded;

  const valueCount =
    Array.isArray(attributeValues) ||
    (attributeValues && typeof attributeValues === "object")
      ? Object.keys(attributeValues).length
      : attributeValues;

  const navItems = [
    { label: "Overview", icon: Gauge },
    { label: "Visualizations", icon: BarChart3 },
    { label: "Association Rules", icon: GitBranch },
  ];

  function navigateTo(label) {
    setActivePage(label);

    const elementId =
      label === "Overview"
        ? "overview"
        : label === "Visualizations"
          ? "visualizations"
          : "association-rules";

    document.getElementById(elementId)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  return (
    <div className="dashboard-shell min-h-screen bg-[#080d18] text-slate-200">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-[#0b1120] p-5 lg:flex lg:flex-col">
          <div className="flex items-center gap-3 px-2 py-3">
            <div className="rounded-xl bg-cyan-400/10 p-2.5 text-cyan-300">
              <Activity size={25} />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                AccidentIQ
              </h1>
              <p className="text-xs text-slate-500">Pattern Discovery</p>
            </div>
          </div>

          <div className="mt-10">
            <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              Workspace
            </p>

            <nav className="mt-3 space-y-1">
              {navItems.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  onClick={() => navigateTo(label)}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm transition ${
                    activePage === label
                      ? "bg-cyan-400/10 font-medium text-cyan-300"
                      : "text-slate-400 hover:bg-slate-800/70 hover:text-white"
                  }`}
                >
                  <Icon size={18} />
                  {label}
                </button>
              ))}
            </nav>
          </div>

          <div className="mt-auto rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
            <p className="text-xs font-semibold text-cyan-300">
              Project context
            </p>
            <p className="mt-3 text-xs leading-6 text-slate-400">
              Identify co-occurring road accident characteristics in the
              dataset using Apriori analysis.
            </p>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="sticky top-0 z-10 border-b border-slate-800 bg-[#0b1120]/95 px-5 py-3 sm:px-7">
            <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span>AccidentIQ</span>
                  <span>/</span>
                  <span className="text-slate-300">{activePage}</span>
                </div>
                <h2 className="mt-1 text-lg font-semibold text-white sm:text-xl">
                  Road Accident Analytics
                </h2>
              </div>

              <div className="flex items-center gap-3">
                <div
                  role="status"
                  aria-live="polite"
                  title={apiHealth.message}
                  className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-2 py-2 sm:px-3"
                >
                  <span
                    className={`size-2 rounded-full ${
                      apiHealth.status === "ready"
                        ? "bg-emerald-400"
                        : apiHealth.status === "checking"
                          ? "animate-pulse bg-amber-400"
                          : "bg-rose-400"
                    }`}
                  />
                  <span className="sr-only text-xs text-slate-300 sm:not-sr-only">
                    {apiHealth.status === "ready"
                      ? "API connected · dataset loaded"
                      : apiHealth.status === "checking"
                        ? "Checking API..."
                        : "API or dataset unavailable"}
                  </span>
                </div>

                <button
                  onClick={() => refreshDashboard()}
                  disabled={loadingStats || apiHealth.status === "checking"}
                  title="Refresh dataset statistics and API status"
                  aria-label="Refresh dashboard data"
                  className="rounded-xl border border-slate-700 bg-slate-900 p-2.5 text-slate-300 transition hover:border-cyan-500 hover:text-cyan-300 disabled:opacity-50"
                >
                  <RefreshCw
                    size={17}
                    className={
                      loadingStats || apiHealth.status === "checking"
                        ? "animate-spin"
                        : ""
                    }
                  />
                </button>
              </div>
            </div>
            <nav
              aria-label="Primary navigation"
              className="mx-auto mt-4 flex max-w-[1600px] gap-2 overflow-x-auto lg:hidden"
            >
              {navItems.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  onClick={() => navigateTo(label)}
                  aria-current={activePage === label ? "page" : undefined}
                  className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${
                    activePage === label
                      ? "bg-cyan-400/10 font-medium text-cyan-300"
                      : "text-slate-400 hover:bg-slate-800/70 hover:text-white"
                  }`}
                >
                  <Icon size={16} />
                  {label}
                </button>
              ))}
            </nav>
          </header>

          <div className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-6">
            {error && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4"
              >
                <CircleAlert
                  className="mt-0.5 shrink-0 text-rose-300"
                  size={19}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-rose-200">
                    Something went wrong
                  </p>
                  <p className="mt-1 break-words text-sm text-rose-200/80">
                    {error}
                  </p>
                </div>
                <button
                  onClick={() => setError("")}
                  aria-label="Dismiss error"
                  className="text-rose-300 hover:text-white"
                >
                  <X size={17} />
                </button>
              </div>
            )}

            {notice && (
              <div className="success-banner flex items-start gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
                <CheckCircle2
                  className="mt-0.5 shrink-0 text-emerald-300"
                  size={19}
                />
                <p className="flex-1 text-sm text-emerald-200">{notice}</p>
                <button
                  onClick={() => setNotice("")}
                  aria-label="Dismiss notification"
                  className="text-emerald-300 hover:text-white"
                >
                  <X size={17} />
                </button>
              </div>
            )}

            <section id="overview" className="scroll-mt-36 space-y-6">
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-cyan-300">
                    Dataset analysis
                  </div>
                  <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                    Road accident patterns
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                    Explore your dataset, identify frequent accident factors,
                    and discover association rules using Apriori. The rules
                    describe patterns in these records, not causes or
                    real-world risk.
                  </p>
                </div>

                <button
                  onClick={handleRun}
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/30 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? (
                    <LoaderCircle size={18} className="animate-spin" />
                  ) : (
                    <Play size={17} fill="currentColor" />
                  )}
                  {loading ? "Analyzing..." : "Analyze Accident Patterns"}
                </button>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  icon={Database}
                  label="Transactions"
                  value={
                    loadingStats
                      ? "..."
                      : transactionCount == null
                        ? "—"
                        : formatNumber(transactionCount)
                  }
                  description="Records available for analysis"
                  accent="bg-cyan-400/10 text-cyan-300"
                />
                <MetricCard
                  icon={CarFront}
                  label="Attributes"
                  value={
                    loadingStats
                      ? "..."
                      : attributeCount == null
                        ? "—"
                        : formatNumber(attributeCount)
                  }
                  description="Attributes reported by preprocessing"
                  accent="bg-violet-400/10 text-violet-300"
                />
                <MetricCard
                  icon={GitBranch}
                  label="Association rules"
                  value={
                    analysisStatus === "success" || analysisStatus === "empty"
                      ? formatNumber(rules.length)
                      : "—"
                  }
                  description="Rules returned by the latest successful analysis"
                  accent="bg-emerald-400/10 text-emerald-300"
                />
                <MetricCard
                  icon={TrendingUp}
                  label="Frequent itemsets"
                  value={
                    frequentItemsetCount == null
                      ? "—"
                      : formatNumber(frequentItemsetCount)
                  }
                  description="Count reported by the mining API"
                  accent="bg-amber-400/10 text-amber-300"
                />
              </div>

              <Panel
                title="Apriori configuration"
                subtitle="Enter your thresholds to control which patterns are returned."
                icon={SlidersHorizontal}
              >
                <div className="grid gap-6 sm:grid-cols-2">
                  <div>
                    <label
                      htmlFor="support"
                      className="mb-2 block text-sm font-medium text-slate-200"
                    >
                      Minimum support
                    </label>
                    <input
                      id="support"
                      type="number"
                      min="0.01"
                      max="1"
                      step="0.01"
                      value={support}
                      onChange={(event) => setSupport(event.target.value)}
                      placeholder="e.g. 0.05"
                      aria-describedby="support-help"
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/10"
                    />
                    <p
                      id="support-help"
                      className="mt-2 text-xs leading-5 text-slate-500"
                    >
                      Minimum share of analyzed records that must contain an
                      itemset. Enter 0.01–1; 0.05 means 5%.
                    </p>
                  </div>

                  <div>
                    <label
                      htmlFor="confidence"
                      className="mb-2 block text-sm font-medium text-slate-200"
                    >
                      Minimum confidence
                    </label>
                    <input
                      id="confidence"
                      type="number"
                      min="0.01"
                      max="1"
                      step="0.01"
                      value={confidence}
                      onChange={(event) => setConfidence(event.target.value)}
                      placeholder="e.g. 0.5"
                      aria-describedby="confidence-help"
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-violet-400 focus:ring-2 focus:ring-violet-400/10"
                    />
                    <p
                      id="confidence-help"
                      className="mt-2 text-xs leading-5 text-slate-500"
                    >
                      Minimum share of records containing the antecedent that
                      must also contain the consequent. Enter 0.01–1; 0.5
                      means 50%.
                    </p>
                  </div>
                </div>

                <div className="mt-6 flex flex-col gap-3 border-t border-slate-800 pt-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="text-xs text-slate-500">
                    <p>Maximum itemset size: 4</p>
                    <p className="mt-1">
                      Current support:{" "}
                      {support.trim() !== "" &&
                      Number.isFinite(Number(support))
                        ? `${(Number(support) * 100).toFixed(1)}%`
                        : "Not set"}{" "}
                      · Current confidence:{" "}
                      {confidence.trim() !== "" &&
                      Number.isFinite(Number(confidence))
                        ? `${(Number(confidence) * 100).toFixed(1)}%`
                        : "Not set"}
                    </p>
                    {lastRun && analysisParameters && (
                      <p className="mt-1">
                        Last successful run: {lastRun.toLocaleTimeString()}{" "}
                        (support {formatPercentage(analysisParameters.support)},
                        confidence{" "}
                        {formatPercentage(analysisParameters.confidence)})
                      </p>
                    )}
                  </div>

                  <button
                    onClick={handleRun}
                    disabled={loading}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loading ? (
                      <LoaderCircle size={17} className="animate-spin" />
                    ) : (
                      <Play size={16} fill="currentColor" />
                    )}
                    {loading
                      ? "Analyzing..."
                      : "Analyze Accident Patterns"}
                  </button>
                </div>
              </Panel>
            </section>

            <section
              id="visualizations"
              className="scroll-mt-36 space-y-5"
            >
              <div>
                <div className="flex items-center gap-2 text-cyan-300">
                  <BarChart3 size={18} />
                  <span className="text-xs font-semibold uppercase tracking-[0.18em]">
                    Visual analytics
                  </span>
                </div>
                <h2 className="mt-2 text-xl font-bold text-white sm:text-2xl">
                  Accident severity and factor frequencies
                </h2>
                <p className="mt-2 text-sm text-slate-400">
                  Interactive Plotly charts based on the dataset and mining API
                  responses.
                </p>
              </div>

              <div className="grid gap-5 xl:grid-cols-2">
                <Panel
                  title="Accident severity distribution"
                  subtitle="Number of analyzed records in each severity category, using dataset item frequencies."
                  icon={ShieldAlert}
                >
                  {severityEntries.length > 0 ? (
                    <Plot
                      data={[
                        {
                          type: "bar",
                          x: severityEntries.map((item) => item.label),
                          y: severityEntries.map((item) => item.count),
                          text: severityEntries.map((item) =>
                            formatNumber(item.count)
                          ),
                          textposition: "outside",
                          cliponaxis: false,
                          marker: {
                            color: ["#22d3ee", "#34d399", "#fbbf24", "#fb7185"],
                          },
                          hovertemplate:
                            "<b>%{x}</b><br>Records: %{y:,}<extra></extra>",
                        },
                      ]}
                      layout={{
                        ...chartLayout,
                        height: 330,
                        margin: { l: 48, r: 55, t: 42, b: 55 },
                        title: {
                          text: "Accident severity distribution",
                          font: { size: 14 },
                        },
                        xaxis: {
                          ...chartLayout.xaxis,
                          title: { text: "Severity category" },
                          type: "category",
                        },
                        yaxis: {
                          ...chartLayout.yaxis,
                          title: { text: "Records (count)" },
                          rangemode: "tozero",
                        },
                      }}
                      config={chartConfig}
                      useResizeHandler
                      style={{ width: "100%" }}
                    />
                  ) : (
                    <EmptyChart
                      message={
                        loadingStats
                          ? "Loading severity frequencies from dataset statistics..."
                          : "Severity categories cannot be charted because usable accident_severity item frequencies are not available in the API statistics."
                      }
                    />
                  )}
                  <KeyInference
                    {...(severityInference || {
                      takeaway: loadingStats
                        ? "Loading severity distribution."
                        : "Severity distribution is unavailable.",
                      evidence: loadingStats
                        ? "Waiting for severity counts from dataset statistics."
                        : "The dataset statistics do not contain usable severity category counts. No values have been estimated.",
                    })}
                  />
                </Panel>

                <Panel
                  title="Most Common Accident Conditions"
                  subtitle="The highest-count recorded category is shown independently for each available condition. Ties are resolved alphabetically."
                  icon={TrendingUp}
                >
                  <p className="mb-4 text-xs leading-5 text-slate-400">
                    Missing records by condition:{" "}
                    {conditionSummaries.length > 0
                      ? conditionSummaries
                          .map(
                            (attribute) =>
                              `${attribute.label}: ${attribute.missingCount === null ? "Missing count unavailable" : formatNumber(attribute.missingCount)}`
                          )
                          .join(" · ")
                      : "Missing counts unavailable."}
                    {" Percentages use "}
                    {Number.isFinite(totalConditionRecords) &&
                    totalConditionRecords > 0
                      ? formatNumber(totalConditionRecords)
                      : "the total"}
                    {" analyzed accident records as the denominator and may not add up to 100% when values are missing."}
                  </p>
                  {commonConditionEntries.length > 0 &&
                  Number.isInteger(totalConditionRecords) &&
                  totalConditionRecords > 0 ? (
                    <Plot
                      data={[
                        {
                          type: "bar",
                          orientation: "h",
                          x: commonConditionEntries
                            .slice()
                            .reverse()
                            .map((item) => item.winner.count),
                          y: commonConditionEntries
                            .slice()
                            .reverse()
                            .map(
                              (item) =>
                                `${item.label}: ${formatItemLabel(item.winner.value)}`
                            ),
                          text: commonConditionEntries
                            .slice()
                            .reverse()
                            .map(
                              (item) =>
                                `${formatNumber(item.winner.count)} (${item.percentage.toFixed(1)}%)`
                            ),
                          customdata: commonConditionEntries
                            .slice()
                            .reverse()
                            .map((item) => [
                              item.label,
                              formatItemLabel(item.winner.value),
                              item.percentage,
                              item.missingCount === null
                                ? "Missing count unavailable"
                                : formatNumber(item.missingCount),
                            ]),
                          textposition: "outside",
                          cliponaxis: false,
                          marker: {
                            color: "#22d3ee",
                            line: { color: "#0891b2", width: 1 },
                          },
                          hovertemplate:
                            "<b>%{customdata[0]}: %{customdata[1]}</b><br>Accident records: %{x:,}<br>Of all analyzed accident records: %{customdata[2]:.1f}%<br>Missing records for condition: %{customdata[3]}<extra></extra>",
                        },
                      ]}
                      layout={{
                        ...chartLayout,
                        height: Math.max(330, commonConditionEntries.length * 58),
                        title: {
                          text: "Highest-count categories by condition",
                          font: { size: 14 },
                        },
                        margin: { l: 210, r: 80, t: 42, b: 50 },
                        xaxis: {
                          ...chartLayout.xaxis,
                          title: { text: "Accident records (count)" },
                          rangemode: "tozero",
                        },
                        yaxis: {
                          ...chartLayout.yaxis,
                          title: { text: "Condition and category" },
                          automargin: true,
                        },
                      }}
                      config={chartConfig}
                      useResizeHandler
                      style={{ width: "100%" }}
                    />
                  ) : (
                    <EmptyChart
                      message={
                        loadingStats
                          ? "Loading condition frequencies from dataset statistics..."
                          : conditionSummaries.length > 0 &&
                              conditionSummaries.every(
                                (attribute) => !attribute.winner
                              )
                            ? "Complete category counts are unavailable for the supported conditions in the dataset statistics."
                            : "No usable frequencies and analyzed-record total are available for these conditions."
                      }
                    />
                  )}
                  {unavailableConditionLabels.length > 0 && (
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      Complete category counts unavailable for:{" "}
                      {unavailableConditionLabels.join(", ")}.
                    </p>
                  )}
                  <KeyInference
                    {...(conditionInference || {
                      takeaway: loadingStats
                        ? "Loading accident condition frequencies."
                        : "Most common accident conditions are unavailable.",
                      evidence: loadingStats
                        ? "Waiting for condition counts from dataset statistics."
                        : "Complete category counts and a valid analyzed-record total are required to compare recorded conditions.",
                    })}
                  />
                </Panel>
              </div>

              <Panel
                title="Confidence vs. lift"
                subtitle="Each point is an actual returned rule. Confidence is shown as a percentage; lift compares observed co-occurrence with the independent baseline (1.0)."
                icon={Activity}
              >
                {rulePoints.length > 0 ? (
                  <Plot
                    data={[
                      {
                        type: "scatter",
                        mode: "markers",
                        x: rulePoints.map((rule) => rule.confidenceValue),
                        y: rulePoints.map((rule) => rule.liftValue),
                        text: rulePoints.map(
                          (rule) => `${rule.condition} → ${rule.result}`
                        ),
                        customdata: rulePoints.map((rule) => [
                          rule.support,
                          rule.confidence,
                          rule.lift,
                        ]),
                        marker: {
                          size: 12,
                          color: rulePoints.map((rule) => rule.liftValue),
                          colorscale: [
                            [0, "#22d3ee"],
                            [0.33, "#34d399"],
                            [0.66, "#fbbf24"],
                            [1, "#fb7185"],
                          ],
                          showscale: true,
                          colorbar: { title: { text: "Lift" } },
                          line: { color: "#ffffff", width: 1 },
                          opacity: 0.9,
                        },
                        hovertemplate:
                          "<b>%{text}</b><br>Support: %{customdata[0]}<br>Confidence: %{customdata[1]}<br>Lift: %{customdata[2]}<extra></extra>",
                      },
                    ]}
                    layout={{
                      ...chartLayout,
                      height: 350,
                      title: {
                        text: "Association-rule confidence vs. lift",
                        font: { size: 14 },
                      },
                      margin: { l: 65, r: 65, t: 42, b: 60 },
                      xaxis: {
                        ...chartLayout.xaxis,
                        title: { text: "Confidence (%)" },
                        ticksuffix: "%",
                      },
                      yaxis: {
                        ...chartLayout.yaxis,
                        title: { text: "Lift (ratio)" },
                      },
                    }}
                    config={chartConfig}
                    useResizeHandler
                    style={{ width: "100%" }}
                  />
                ) : (
                  <EmptyChart
                    message={
                      analysisStatus === "loading"
                        ? "Mining association rules..."
                        : analysisStatus === "empty"
                          ? `No rules met support ${formatPercentage(analysisParameters?.support)} and confidence ${formatPercentage(analysisParameters?.confidence)}. Try adjusting the thresholds.`
                          : analysisStatus === "error"
                            ? "The latest analysis failed. See the error message above and retry after resolving the API or dataset issue."
                            : rules.length > 0
                              ? "Rules were returned, but valid confidence and lift metrics are not available for plotting."
                              : "Set minimum support and confidence, then analyze the dataset to see qualifying rules."
                    }
                  />
                )}
                <KeyInference
                  {...(associationInference || {
                    takeaway:
                      analysisStatus === "empty"
                        ? "No rules met the selected thresholds."
                        : analysisStatus === "error"
                          ? "No inference is available."
                          : "Association inference is unavailable.",
                    evidence:
                      analysisStatus === "empty"
                        ? "Try adjusting the thresholds to explore other rule sets."
                        : analysisStatus === "error"
                          ? "The latest analysis did not complete successfully."
                          : rules.length > 0
                            ? "Valid confidence and lift values were not returned for these rules."
                            : "Run an analysis to see an inference based on returned confidence and lift metrics.",
                  })}
                />
                <p className="mt-3 text-xs leading-5 text-slate-500">
                  These rules identify associations within recorded accident
                  data. They do not establish causation or prove that a
                  condition increases accident risk.
                </p>
              </Panel>
            </section>

            <section
              id="association-rules"
              className="scroll-mt-36 space-y-5"
            >
              <div>
                <div className="flex items-center gap-2 text-violet-300">
                  <GitBranch size={18} />
                  <span className="text-xs font-semibold uppercase tracking-[0.18em]">
                    Pattern discovery
                  </span>
                </div>
                <h2 className="mt-2 text-xl font-bold text-white sm:text-2xl">
                  Association rules
                </h2>
                <p className="mt-2 text-sm text-slate-400">
                  Review each returned rule’s antecedent, consequent, support,
                  confidence, lift, and plain-language interpretation.
                </p>
              </div>

              <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
                <div className="flex flex-col gap-3 border-b border-slate-800 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-white">
                      Discovered patterns
                    </h3>
                    <p className="mt-1 text-xs text-slate-500">
                      {analysisStatus === "success"
                        ? `${rules.length} rule(s) from the latest successful analysis`
                        : analysisStatus === "empty"
                          ? "No rules met the latest selected thresholds"
                          : analysisStatus === "loading"
                            ? "Analysis in progress"
                            : analysisStatus === "error"
                              ? "Latest analysis did not complete"
                              : "Run an analysis to discover rules"}
                    </p>
                  </div>

                  {analysisParameters && (
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded-lg bg-cyan-400/10 px-3 py-2 text-cyan-300">
                        Minimum support:{" "}
                        {formatPercentage(analysisParameters.support)}
                      </span>
                      <span className="rounded-lg bg-violet-400/10 px-3 py-2 text-violet-300">
                        Minimum confidence:{" "}
                        {formatPercentage(analysisParameters.confidence)}
                      </span>
                    </div>
                  )}
                </div>

                {loading ? (
                  <div className="flex min-h-64 flex-col items-center justify-center gap-3">
                    <LoaderCircle
                      className="animate-spin text-cyan-300"
                      size={30}
                    />
                    <p className="text-sm text-slate-300">
                      Mining frequent itemsets and association rules...
                    </p>
                    <p className="text-xs text-slate-500">
                      This may take a moment depending on the dataset.
                    </p>
                  </div>
                ) : rules.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="rules-table w-full min-w-[1040px] text-left text-sm">
                      <thead className="bg-slate-950/50 text-xs uppercase tracking-wider text-slate-500">
                        <tr>
                          <th className="px-5 py-4 font-medium">#</th>
                          <th className="px-5 py-4 font-medium">
                            Antecedent
                          </th>
                          <th className="px-5 py-4 font-medium">Consequent</th>
                          <th className="px-5 py-4 font-medium">
                            Support (%)
                          </th>
                          <th className="px-5 py-4 font-medium">
                            Confidence (%)
                          </th>
                          <th className="px-5 py-4 font-medium">
                            Lift (ratio)
                          </th>
                          <th className="px-5 py-4 font-medium">
                            Plain-language reading
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {rules.map((rule) => (
                          <tr
                            key={rule.id}
                            className="transition hover:bg-slate-800/30"
                          >
                            <td className="px-5 py-4 text-slate-500">
                              {rule.id}
                            </td>
                            <td className="rule-antecedent max-w-64 whitespace-normal px-5 py-4 text-slate-200">
                              {rule.condition}
                            </td>
                            <td className="rule-consequent max-w-64 whitespace-normal px-5 py-4 text-cyan-200">
                              {rule.result}
                            </td>
                            <td className="rule-support px-5 py-4 font-mono text-slate-300">
                              {rule.support}
                            </td>
                            <td className="px-5 py-4">
                              <span className="rounded-md bg-emerald-400/10 px-2 py-1 font-mono text-emerald-300">
                                {rule.confidence}
                              </span>
                            </td>
                            <td className="rule-lift px-5 py-4 font-mono text-violet-300">
                              {rule.lift}
                            </td>
                            <td className="rule-explanation max-w-sm whitespace-normal px-5 py-4 text-xs leading-5 text-slate-400">
                              When {rule.condition} appears, {rule.result} also
                              appears
                              {rule.confidence !== "—" &&
                                ` in ${rule.confidence} of records containing the antecedent`}
                              ; lift is {rule.lift}.
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="flex min-h-64 flex-col items-center justify-center px-6 text-center">
                    <div className="rounded-2xl bg-slate-800 p-4 text-slate-400">
                      <GitBranch size={27} />
                    </div>
                    <h3 className="mt-4 font-medium text-white">
                      {analysisStatus === "empty"
                        ? "No rules met these thresholds"
                        : analysisStatus === "error"
                          ? "Analysis could not be completed"
                          : "No association rules to display yet"}
                    </h3>
                    <p className="mt-2 max-w-md text-sm leading-6 text-slate-400">
                      {analysisStatus === "empty"
                        ? `The API returned no rules for minimum support ${formatPercentage(analysisParameters?.support)} and minimum confidence ${formatPercentage(analysisParameters?.confidence)}. Adjust the thresholds and analyze again.`
                        : analysisStatus === "error"
                          ? "The latest request failed; no previous rules are shown as current results. Review the error above and retry when the API and dataset are available."
                          : "Choose minimum support and confidence above, then analyze the dataset to retrieve rules from the API."}
                    </p>
                    <button
                      onClick={handleRun}
                      disabled={loading}
                      className="mt-5 inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
                    >
                      <Play size={15} />
                      Analyze Accident Patterns
                    </button>
                  </div>
                )}
              </div>
            </section>

            <footer className="border-t border-slate-800 py-6">
              <div className="flex flex-col gap-2 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                <p>AccidentIQ · Road Accident Pattern Discovery</p>
                <p className="flex items-center gap-2">
                  <span className="size-1.5 rounded-full bg-cyan-400" />
                  Apriori association rule mining
                </p>
              </div>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
