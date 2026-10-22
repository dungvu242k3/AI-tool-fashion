"""Grounded JSON analysis, one repair attempt, then observed-data-only output."""
from src.analyzers.analysis_policy import AnalysisPolicy
from src.analyzers.evidence_catalog import EvidenceCatalog
from src.analyzers.grounded_prompt import SYSTEM, build_prompt
from src.analyzers.grounded_validator import validate_analysis
from src.analyzers.ollama_client import GenerationError, OllamaClient, validate_local_model
from src.analyzers.strict_json import AnalysisValidationError
from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from src.models.analysis import ANALYSIS_VERSION
from src.processors.data_quality import has_sufficient_evidence
from src.reporters.evidence_renderer import EvidenceRenderer
from src.reporters.grounded_renderer import GroundedRenderer
from src.reporters.ranking_renderer import RankingRenderer


class LLMAnalyzer:
    def __init__(self, model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, fast_mode=False, http_client=None,
                 *, policy=None, generation_client=None):
        self.model, self.fast_mode = model, fast_mode
        self.policy = policy if policy is not None else AnalysisPolicy()
        if not isinstance(self.policy, AnalysisPolicy):
            raise TypeError("AnalysisPolicy required")
        if http_client is not None and generation_client is not None:
            raise ValueError("Inject an HTTP session or generation client, not both")
        self._owned = generation_client is None
        self.client = (generation_client if generation_client is not None else
                       OllamaClient(base_url, OLLAMA_TIMEOUT, self.policy, session=http_client))
        self.attempted = False

    def _call_ollama(self, prompt, system=SYSTEM):
        return self.client.generate(self.model, prompt, system)

    def analyze(self, niche_name, data):
        journal = {"schema_version": ANALYSIS_VERSION, "policy": self.policy.to_dict(), "attempts": [], "outcome": "not_requested"}
        def fallback(status, code):
            journal["outcome"] = code
            section = EvidenceRenderer.section(data, status, [f"[{code}] Không sử dụng claim/ý tưởng AI; chỉ giữ dữ kiện nguồn."])
            section.ai_validation = journal
            return section

        if niche_name != data.niche_name or not has_sufficient_evidence(data):
            return fallback("insufficient_data", "quality_gate_not_passed_or_evidence_changed")
        if self.fast_mode:
            section = EvidenceRenderer.section(data, "not_requested")
            section.ai_validation = journal
            return section
        try:
            validate_local_model(self.model)
        except GenerationError as exc:
            return fallback("context_rejected", exc.code)
        try:
            catalog = EvidenceCatalog.from_data(data, self.policy)
            journal["context"] = catalog.context_summary()
        except AnalysisValidationError as exc:
            return fallback("context_rejected", exc.code)
        errors = ()
        for attempt in range(1, 3):
            if not has_sufficient_evidence(data) or data.quality_assessment.data_digest != catalog.evidence_digest:
                return fallback("insufficient_data", "evidence_changed_during_generation")
            try:
                prompt = build_prompt(catalog, self.policy, errors)
            except AnalysisValidationError as exc:
                return fallback("context_rejected", exc.code)
            self.attempted = True
            trace = {"attempt": attempt, "status": "rejected", "errors": []}
            journal["attempts"].append(trace)
            try:
                generated = self._call_ollama(prompt, system=SYSTEM)
                if generated == "":
                    raise GenerationError("empty_generation", repairable=True)
                analysis = validate_analysis(generated, catalog, max_bytes=self.policy.max_response_bytes)
            except GenerationError as exc:
                trace["status"] = "invalid_output" if exc.repairable else "transport_failed"
                error = AnalysisValidationError(exc.code)
                trace["errors"] = [error.to_dict()]
                if exc.http_status is not None:
                    trace["http_status"] = exc.http_status
                if not exc.repairable:
                    return fallback("failed", exc.code)
                errors = (error,)
            except AnalysisValidationError as exc:
                trace["errors"] = [exc.to_dict()]
                errors = (exc,)
            else:
                if not has_sufficient_evidence(data) or data.quality_assessment.data_digest != catalog.evidence_digest:
                    return fallback("insufficient_data", "evidence_changed_during_generation")
                trace["status"] = "accepted"
                journal["outcome"] = "source_references_verified"
                return GroundedRenderer.section(data, analysis, catalog, journal)
        return fallback("invalid_output", "grounding_rejected_after_one_repair")

    def summarize(self, niche_results, *, ranking_assessment=None, analysis_summary=None):
        """Read-only compatibility entry; never ask a model to invent a ranking."""
        return RankingRenderer.summary(ranking_assessment, niche_results, analysis_summary)

    def close(self):
        if self._owned:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
