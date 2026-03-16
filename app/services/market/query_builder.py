from typing import Dict, List


class QueryBuilder:
    @staticmethod
    def build_queries(product: Dict) -> List[str]:
        brand = (product.get("brand") or "").strip()
        model = (product.get("model") or "").strip()
        storage = (product.get("storage") or "").strip()
        category = (product.get("category") or "").strip()

        queries: list[str] = []

        if model:
            queries.append(model)

            compact_model = (
                model.replace(" ", "")
                .replace("-", "")
                .replace("_", "")
            )
            if compact_model != model:
                queries.append(compact_model)

        if brand and model:
            queries.append(f"{brand} {model}")

        if model and storage:
            queries.append(f"{model} {storage}")

        if brand and model and storage:
            queries.append(f"{brand} {model} {storage}")

        if category and model:
            queries.append(f"{model} {category}")

        if not queries and category:
            queries.append(category)

        # 중복 제거 + 빈 문자열 제거
        deduped = []
        seen = set()
        for q in queries:
            normalized = q.strip()
            if normalized and normalized not in seen:
                deduped.append(normalized)
                seen.add(normalized)

        return deduped