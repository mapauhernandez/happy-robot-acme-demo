"""Endpoint serving the in-app dashboard for negotiation analytics."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Negotiation Insights Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha384-Ata0yv43bLulTn60uMAsqRX0n+sW6V1fyf6cTGP5N3Fr5Do6t7P2RnCO1q5GBuVJ" crossorigin="anonymous"></script>
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 0;
            padding: 0 1.5rem 3rem;
            background-color: #f5f6fa;
        }
        header {
            padding: 1.5rem 0;
            text-align: center;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
        }
        .card {
            background: #fff;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            box-shadow: 0 10px 25px rgba(31, 45, 61, 0.08);
        }
        form {
            background: #fff;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(31, 45, 61, 0.08);
            margin-bottom: 2rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem 1.5rem;
        }
        label {
            font-weight: 600;
            display: flex;
            flex-direction: column;
            font-size: 0.9rem;
        }
        input, select {
            margin-top: 0.35rem;
            padding: 0.6rem 0.75rem;
            border-radius: 8px;
            border: 1px solid #d0d7de;
            font-size: 0.95rem;
        }
        button {
            grid-column: 1 / -1;
            padding: 0.75rem 1.25rem;
            border-radius: 8px;
            border: none;
            background: #2563eb;
            color: #fff;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover {
            background: #1d4ed8;
        }
        .controls {
            margin: 1rem 0 2rem;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            align-items: center;
        }
        .status {
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>Negotiation Insights Dashboard</h1>
        <p>Submit load negotiation outcomes and explore acceptance trends.</p>
    </header>
    <form id="negotiation-form">
        <label>Load Accepted
            <select name="load_accepted" required>
                <option value="true">Accepted</option>
                <option value="false">Not Accepted</option>
            </select>
        </label>
        <label>Posted Price ($)
            <input type="text" name="posted_price" placeholder="e.g. 1500" required />
        </label>
        <label>Final Price ($)
            <input type="text" name="final_price" placeholder="e.g. 1800" required />
        </label>
        <label>Total Negotiations
            <input type="text" name="total_negotiations" placeholder="e.g. 3" required />
        </label>
        <label>Call Sentiment
            <input type="text" name="call_sentiment" placeholder="e.g. Positive" required />
        </label>
        <label>Commodity
            <input type="text" name="commodity" placeholder="e.g. Steel" required />
        </label>
        <button type="submit">Submit Negotiation</button>
        <div class="status" id="form-status"></div>
    </form>
    <div class="controls">
        <label for="load-filter"><strong>Show records:</strong></label>
        <select id="load-filter">
            <option value="all">All Loads</option>
            <option value="accepted">Accepted Only</option>
            <option value="rejected">Not Accepted Only</option>
        </select>
    </div>
    <div class="grid">
        <div class="card">
            <h2>Difference between posted price and final offer</h2>
            <canvas id="price-diff-chart" aria-label="Price difference chart"></canvas>
        </div>
        <div class="card">
            <h2>Final price</h2>
            <canvas id="final-price-chart" aria-label="Final price chart"></canvas>
        </div>
        <div class="card">
            <h2>Total number of negotiations</h2>
            <canvas id="negotiation-count-chart" aria-label="Total negotiations chart"></canvas>
        </div>
        <div class="card">
            <h2>Call sentiment</h2>
            <canvas id="sentiment-chart" aria-label="Call sentiment chart"></canvas>
        </div>
        <div class="card">
            <h2>Commodity breakdown</h2>
            <canvas id="commodity-chart" aria-label="Commodity chart"></canvas>
        </div>
    </div>
    <script>
        const API_KEY = localStorage.getItem('demoApiKey') || 'local-dev-api-key';
        const charts = {};

        async function fetchNegotiations() {
            const response = await fetch('/negotiations', {
                headers: { 'X-API-Key': API_KEY }
            });
            if (!response.ok) {
                throw new Error('Failed to load negotiations');
            }
            return await response.json();
        }

        function histogram(values, binSize) {
            if (!values.length) {
                return { labels: [], data: [] };
            }

            const min = Math.min(...values);
            const max = Math.max(...values);
            if (min === max) {
                const label = `$${min.toFixed(2)}`;
                return { labels: [label], data: [values.length] };
            }

            const start = Math.floor(min / binSize) * binSize;
            const end = Math.ceil(max / binSize) * binSize;
            const buckets = [];
            for (let value = start; value <= end; value += binSize) {
                const upper = value + binSize;
                const label = `$${value.toFixed(0)} - $${upper.toFixed(0)}`;
                buckets.push({ label, min: value, max: upper, count: 0 });
            }

            for (const value of values) {
                const bucketIndex = Math.min(
                    buckets.length - 1,
                    Math.max(0, Math.floor((value - start) / binSize))
                );
                buckets[bucketIndex].count += 1;
            }

            return {
                labels: buckets.map(bucket => bucket.label),
                data: buckets.map(bucket => bucket.count)
            };
        }

        function countBy(values, key) {
            const counts = new Map();
            for (const value of values) {
                const bucket = key(value);
                counts.set(bucket, (counts.get(bucket) || 0) + 1);
            }
            return {
                labels: Array.from(counts.keys()),
                data: Array.from(counts.values())
            };
        }

        function ensureChart(id, config) {
            if (charts[id]) {
                charts[id].data.labels = config.data.labels;
                charts[id].data.datasets[0].data = config.data.datasets[0].data;
                charts[id].update();
                return charts[id];
            }
            const ctx = document.getElementById(id).getContext('2d');
            charts[id] = new Chart(ctx, config);
            return charts[id];
        }

        function updateCharts(data) {
            const priceDiffs = data.map(item => item.final_price - item.posted_price);
            const finalPrices = data.map(item => item.final_price);
            const negotiationCounts = data.map(item => item.total_negotiations);

            const priceDiffHistogram = histogram(priceDiffs, 100);
            ensureChart('price-diff-chart', {
                type: 'bar',
                data: {
                    labels: priceDiffHistogram.labels,
                    datasets: [{
                        label: 'Loads',
                        backgroundColor: '#2563eb',
                        data: priceDiffHistogram.data
                    }]
                },
                options: {
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: 'Dollars' }
                        },
                        x: { title: { display: true, text: 'Price ranges' } }
                    }
                }
            });

            const finalPriceHistogram = histogram(finalPrices, 100);
            ensureChart('final-price-chart', {
                type: 'bar',
                data: {
                    labels: finalPriceHistogram.labels,
                    datasets: [{
                        label: 'Loads',
                        backgroundColor: '#22c55e',
                        data: finalPriceHistogram.data
                    }]
                },
                options: {
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: 'Dollars' }
                        },
                        x: { title: { display: true, text: 'Price ranges' } }
                    }
                }
            });

            const negotiationHistogram = histogram(negotiationCounts, 1);
            ensureChart('negotiation-count-chart', {
                type: 'bar',
                data: {
                    labels: negotiationHistogram.labels,
                    datasets: [{
                        label: 'Loads',
                        backgroundColor: '#f97316',
                        data: negotiationHistogram.data
                    }]
                },
                options: {
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: 'Count of loads' }
                        },
                        x: { title: { display: true, text: 'Number of negotiations' } }
                    }
                }
            });

            const sentimentCounts = countBy(data, item => item.call_sentiment);
            ensureChart('sentiment-chart', {
                type: 'bar',
                data: {
                    labels: sentimentCounts.labels,
                    datasets: [{
                        label: 'Loads',
                        backgroundColor: '#a855f7',
                        data: sentimentCounts.data
                    }]
                },
                options: {
                    scales: {
                        y: { beginAtZero: true, title: { display: true, text: 'Loads' } },
                        x: { title: { display: true, text: 'Sentiment' } }
                    }
                }
            });

            const commodityCounts = countBy(data, item => item.commodity);
            ensureChart('commodity-chart', {
                type: 'bar',
                data: {
                    labels: commodityCounts.labels,
                    datasets: [{
                        label: 'Loads',
                        backgroundColor: '#0ea5e9',
                        data: commodityCounts.data
                    }]
                },
                options: {
                    scales: {
                        y: { beginAtZero: true, title: { display: true, text: 'Loads' } },
                        x: { title: { display: true, text: 'Commodity' } }
                    }
                }
            });
        }

        async function refreshDashboard() {
            try {
                const filter = document.getElementById('load-filter').value;
                const allData = await fetchNegotiations();
                let filtered = allData;
                if (filter === 'accepted') {
                    filtered = allData.filter(item => item.load_accepted);
                } else if (filter === 'rejected') {
                    filtered = allData.filter(item => !item.load_accepted);
                }
                updateCharts(filtered);
            } catch (error) {
                console.error(error);
                alert('Unable to refresh dashboard data. Ensure the API key is valid.');
            }
        }

        document.getElementById('load-filter').addEventListener('change', refreshDashboard);

        document.getElementById('negotiation-form').addEventListener('submit', async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const status = document.getElementById('form-status');
            status.textContent = 'Submitting…';
            const formData = new FormData(form);
            const payload = Object.fromEntries(formData.entries());

            try {
                const response = await fetch('/negotiations', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error('Request failed');
                }

                status.textContent = 'Saved! Reloading charts…';
                form.reset();
                await refreshDashboard();
                status.textContent = 'Entry saved successfully.';
            } catch (error) {
                status.textContent = 'Unable to save entry. Check the API key and inputs.';
            }
        });

        refreshDashboard();
    </script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve a lightweight dashboard for negotiation insights."""

    return HTMLResponse(DASHBOARD_HTML)
