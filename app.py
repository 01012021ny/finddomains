"""
Abandoned Domain Finder — веб-приложение.
Ищет брошенные домены с ценным контентом для восстановления.
"""

from flask import Flask, render_template, request, jsonify
from domain_checker import analyze_domain, analyze_domains_batch, DomainReport
from expired_sources import (
    generate_keyword_domains,
    search_wayback_by_keyword,
    get_niches,
)

app = Flask(__name__)


@app.route("/")
def index():
    niches = get_niches()
    return render_template("index.html", niches=niches)


@app.route("/api/check", methods=["POST"])
def api_check_domain():
    """Проверить один домен."""
    data = request.get_json()
    domain = data.get("domain", "").strip()
    if not domain:
        return jsonify({"error": "Укажите домен"}), 400

    report = analyze_domain(domain)
    return jsonify(report.to_dict())


@app.route("/api/check-batch", methods=["POST"])
def api_check_batch():
    """Проверить список доменов."""
    data = request.get_json()
    domains = data.get("domains", [])
    if not domains:
        return jsonify({"error": "Укажите список доменов"}), 400

    domains = domains[:20]  # лимит 20 доменов за раз
    results = analyze_domains_batch(domains, delay=0.5)
    return jsonify([r.to_dict() for r in results])


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Сгенерировать домены по нише."""
    data = request.get_json()
    niche = data.get("niche", "")
    if not niche:
        return jsonify({"error": "Выберите нишу"}), 400

    domains = generate_keyword_domains(niche)
    return jsonify({"domains": domains, "count": len(domains)})


@app.route("/api/search-archive", methods=["POST"])
def api_search_archive():
    """Поиск доменов по ключевому слову в Wayback Machine."""
    data = request.get_json()
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "Введите ключевое слово"}), 400

    domains = search_wayback_by_keyword(keyword, limit=20)
    return jsonify({"domains": domains, "count": len(domains)})


@app.route("/api/niches")
def api_niches():
    """Список доступных ниш."""
    return jsonify(get_niches())


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
