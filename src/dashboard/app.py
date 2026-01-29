"""FastAPI application for the web dashboard."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..utils.config import ConfigManager
from .routes import create_router

logger = logging.getLogger(__name__)


def create_app(
    config_manager: Optional[ConfigManager] = None,
    value_bets_store: Optional[list] = None,
    fixtures_store: Optional[list] = None,
) -> FastAPI:
    """
    Create the FastAPI application.

    Args:
        config_manager: Optional ConfigManager instance
        value_bets_store: Optional list to store current value bets
        fixtures_store: Optional list to store current fixtures

    Returns:
        Configured FastAPI application
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        logger.info("Dashboard starting up")
        yield
        logger.info("Dashboard shutting down")

    app = FastAPI(
        title="Soccer Props Value Betting",
        description="Monitor and find value betting opportunities in soccer player props",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize shared state
    if config_manager is None:
        config_manager = ConfigManager()

    if value_bets_store is None:
        value_bets_store = []

    if fixtures_store is None:
        fixtures_store = []

    # Store in app state
    app.state.config_manager = config_manager
    app.state.value_bets = value_bets_store
    app.state.fixtures = fixtures_store

    # Add API routes
    router = create_router()
    app.include_router(router, prefix="/api")

    # Serve static files (Vue.js frontend)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    else:
        # Serve a simple HTML page if no static files
        from fastapi.responses import HTMLResponse

        @app.get("/", response_class=HTMLResponse)
        async def root():
            return get_default_html()

    return app


def get_default_html() -> str:
    """Return default HTML when static files aren't available."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Soccer Props Value Betting</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div id="app">
        <nav class="bg-green-600 text-white p-4 shadow-lg">
            <div class="container mx-auto flex justify-between items-center">
                <h1 class="text-xl font-bold">⚽ Soccer Props Value Betting</h1>
                <div class="flex gap-4">
                    <button @click="currentTab = 'bets'"
                            :class="currentTab === 'bets' ? 'bg-green-700' : ''"
                            class="px-4 py-2 rounded hover:bg-green-700">
                        Value Bets
                    </button>
                    <button @click="currentTab = 'fixtures'"
                            :class="currentTab === 'fixtures' ? 'bg-green-700' : ''"
                            class="px-4 py-2 rounded hover:bg-green-700">
                        Fixtures
                    </button>
                    <button @click="currentTab = 'tracking'"
                            :class="currentTab === 'tracking' ? 'bg-green-700' : ''"
                            class="px-4 py-2 rounded hover:bg-green-700">
                        Tracking
                    </button>
                    <button @click="currentTab = 'settings'"
                            :class="currentTab === 'settings' ? 'bg-green-700' : ''"
                            class="px-4 py-2 rounded hover:bg-green-700">
                        Settings
                    </button>
                </div>
            </div>
        </nav>

        <main class="container mx-auto p-6">
            <!-- Value Bets Tab -->
            <div v-if="currentTab === 'bets'">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-2xl font-bold text-gray-800">Current Value Bets</h2>
                    <button @click="fetchValueBets"
                            class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
                        Refresh
                    </button>
                </div>

                <!-- Filters -->
                <div class="bg-white rounded-lg shadow p-4 mb-6">
                    <div class="grid grid-cols-2 md:grid-cols-6 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Min Edge %</label>
                            <select v-model="filters.minEdge" class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                                <option value="0">All</option>
                                <option value="5">5%+</option>
                                <option value="10">10%+</option>
                                <option value="15">15%+</option>
                                <option value="20">20%+</option>
                                <option value="25">25%+</option>
                                <option value="30">30%+</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Min Odds</label>
                            <input type="number" v-model.number="filters.minOdds" step="0.1" min="1" placeholder="e.g. 1.5"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Max Odds</label>
                            <input type="number" v-model.number="filters.maxOdds" step="0.1" min="1" placeholder="e.g. 5.0"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Market Type</label>
                            <select v-model="filters.market" class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                                <option value="">All Markets</option>
                                <option value="Player Shots">Player Shots</option>
                                <option value="Player Shots On Target">Player Shots On Target</option>
                                <option value="Player Goals">Player Goals</option>
                                <option value="Player Assists">Player Assists</option>
                                <option value="Player Fouls">Player Fouls</option>
                                <option value="Player Cards">Player Cards</option>
                                <option value="Total Shots">Total Shots</option>
                                <option value="Total Corners">Total Corners</option>
                                <option value="Asian Handicap">Asian Handicap</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Bookmaker</label>
                            <select v-model="filters.book" class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                                <option value="">All Books</option>
                                <option value="Betsson">Betsson</option>
                                <option value="LeoVegas">LeoVegas</option>
                                <option value="Unibet">Unibet</option>
                                <option value="Betway">Betway</option>
                            </select>
                        </div>
                        <div class="flex items-end">
                            <button @click="resetFilters" class="w-full bg-gray-200 text-gray-700 px-4 py-2 rounded hover:bg-gray-300">
                                Reset
                            </button>
                        </div>
                    </div>
                    <div class="mt-3 text-sm text-gray-600">
                        Showing <span class="font-bold text-green-600">{{ filteredBets.length }}</span> of {{ valueBets.length }} value bets
                    </div>
                </div>

                <div v-if="loading" class="text-center py-8">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-green-600 border-t-transparent"></div>
                </div>

                <div v-else-if="filteredBets.length === 0" class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                    No value bets match your filters. Try adjusting the criteria.
                </div>

                <div v-else class="grid gap-4">
                    <div v-for="bet in filteredBets" :key="bet.fixture_id + bet.market + bet.selection"
                         class="bg-white rounded-lg shadow p-4 hover:shadow-lg transition-shadow">
                        <div class="flex justify-between items-start mb-3">
                            <div>
                                <h3 class="font-bold text-xl text-blue-600">{{ bet.selection }}</h3>
                                <p class="text-gray-600 font-medium">{{ bet.market }}</p>
                                <p class="text-sm text-gray-500">{{ bet.fixture_name }} &bull; {{ bet.league }}</p>
                            </div>
                            <div class="text-right">
                                <span class="inline-block bg-green-100 text-green-800 px-3 py-1 rounded-full font-bold text-lg">
                                    +{{ bet.edge_percent.toFixed(1) }}%
                                </span>
                            </div>
                        </div>
                        <div class="grid grid-cols-4 gap-4 text-center bg-gray-50 rounded p-3">
                            <div>
                                <p class="text-xs text-gray-500 uppercase">Best Odds</p>
                                <p class="font-bold text-green-600 text-lg">{{ bet.best_odds.toFixed(2) }}</p>
                            </div>
                            <div>
                                <p class="text-xs text-gray-500 uppercase">Book</p>
                                <p class="font-semibold">{{ bet.best_book }}</p>
                            </div>
                            <div>
                                <p class="text-xs text-gray-500 uppercase">Fair Odds</p>
                                <p class="font-semibold">{{ bet.fair_odds.toFixed(2) }}</p>
                            </div>
                            <div>
                                <p class="text-xs text-gray-500 uppercase">All Books</p>
                                <p class="text-xs">
                                    <span v-for="(odds, book) in bet.all_odds" :key="book" class="mr-2">
                                        {{ book }}: {{ odds.toFixed(2) }}
                                    </span>
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Fixtures Tab -->
            <div v-if="currentTab === 'fixtures'">
                <h2 class="text-2xl font-bold text-gray-800 mb-6">Upcoming Fixtures</h2>
                <div v-if="fixtures.length === 0" class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                    No fixtures loaded. The system will fetch fixtures automatically.
                </div>
                <div v-else class="bg-white rounded-lg shadow overflow-hidden">
                    <table class="w-full">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-4 py-3 text-left text-sm font-semibold text-gray-600">Match</th>
                                <th class="px-4 py-3 text-left text-sm font-semibold text-gray-600">League</th>
                                <th class="px-4 py-3 text-left text-sm font-semibold text-gray-600">Kickoff</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="fixture in fixtures" :key="fixture.id" class="border-t">
                                <td class="px-4 py-3">{{ fixture.home_team.name }} vs {{ fixture.away_team.name }}</td>
                                <td class="px-4 py-3 text-gray-600">{{ fixture.league.name }}</td>
                                <td class="px-4 py-3 text-gray-600">{{ formatDate(fixture.start_date) }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Tracking Tab -->
            <div v-if="currentTab === 'tracking'">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Forward Testing Performance</h2>
                    <div class="flex gap-2">
                        <button @click="logBetsForTracking"
                                class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                            Log Current Bets (10%+ Edge)
                        </button>
                        <button @click="checkResults"
                                class="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700">
                            Check Results
                        </button>
                        <button @click="fetchTrackingData"
                                class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
                            Refresh
                        </button>
                    </div>
                </div>

                <!-- Stats Cards -->
                <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                    <div class="bg-white rounded-lg shadow p-4 text-center">
                        <p class="text-sm text-gray-500 uppercase">Total Bets</p>
                        <p class="text-2xl font-bold text-gray-800">{{ trackingStats.total_bets }}</p>
                    </div>
                    <div class="bg-white rounded-lg shadow p-4 text-center">
                        <p class="text-sm text-gray-500 uppercase">Win Rate</p>
                        <p class="text-2xl font-bold" :class="trackingStats.win_rate >= 50 ? 'text-green-600' : 'text-red-600'">
                            {{ trackingStats.win_rate.toFixed(1) }}%
                        </p>
                    </div>
                    <div class="bg-white rounded-lg shadow p-4 text-center">
                        <p class="text-sm text-gray-500 uppercase">ROI</p>
                        <p class="text-2xl font-bold" :class="trackingStats.roi >= 0 ? 'text-green-600' : 'text-red-600'">
                            {{ trackingStats.roi.toFixed(1) }}%
                        </p>
                    </div>
                    <div class="bg-white rounded-lg shadow p-4 text-center">
                        <p class="text-sm text-gray-500 uppercase">Total Profit</p>
                        <p class="text-2xl font-bold" :class="trackingStats.total_profit >= 0 ? 'text-green-600' : 'text-red-600'">
                            {{ trackingStats.total_profit >= 0 ? '+' : '' }}{{ trackingStats.total_profit.toFixed(2) }}
                        </p>
                    </div>
                    <div class="bg-white rounded-lg shadow p-4 text-center">
                        <p class="text-sm text-gray-500 uppercase">Avg Edge</p>
                        <p class="text-2xl font-bold text-blue-600">{{ trackingStats.avg_edge.toFixed(1) }}%</p>
                    </div>
                </div>

                <!-- Record Summary -->
                <div class="bg-white rounded-lg shadow p-4 mb-6">
                    <div class="flex justify-center gap-8">
                        <div class="text-center">
                            <span class="text-3xl font-bold text-green-600">{{ trackingStats.won }}</span>
                            <p class="text-sm text-gray-500">Won</p>
                        </div>
                        <div class="text-center">
                            <span class="text-3xl font-bold text-red-600">{{ trackingStats.lost }}</span>
                            <p class="text-sm text-gray-500">Lost</p>
                        </div>
                        <div class="text-center">
                            <span class="text-3xl font-bold text-gray-600">{{ trackingStats.pushed }}</span>
                            <p class="text-sm text-gray-500">Push</p>
                        </div>
                        <div class="text-center">
                            <span class="text-3xl font-bold text-yellow-600">{{ trackingStats.pending }}</span>
                            <p class="text-sm text-gray-500">Pending</p>
                        </div>
                    </div>
                </div>

                <!-- Tracked Bets List -->
                <h3 class="text-xl font-bold text-gray-800 mb-4">Tracked Bets</h3>
                <div v-if="trackedBets.length === 0" class="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                    No bets tracked yet. Click "Log Current Bets" to start tracking value bets.
                </div>
                <div v-else class="bg-white rounded-lg shadow overflow-hidden">
                    <table class="w-full">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-4 py-3 text-left text-sm font-semibold text-gray-600">Selection</th>
                                <th class="px-4 py-3 text-left text-sm font-semibold text-gray-600">Match</th>
                                <th class="px-4 py-3 text-center text-sm font-semibold text-gray-600">Odds</th>
                                <th class="px-4 py-3 text-center text-sm font-semibold text-gray-600">Edge</th>
                                <th class="px-4 py-3 text-center text-sm font-semibold text-gray-600">Status</th>
                                <th class="px-4 py-3 text-center text-sm font-semibold text-gray-600">P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="bet in trackedBets" :key="bet.id" class="border-t hover:bg-gray-50">
                                <td class="px-4 py-3">
                                    <div class="font-medium text-blue-600">{{ bet.selection }}</div>
                                    <div class="text-xs text-gray-500">{{ bet.market }} @ {{ bet.best_book }}</div>
                                </td>
                                <td class="px-4 py-3">
                                    <div class="text-sm">{{ bet.fixture_name }}</div>
                                    <div class="text-xs text-gray-500">{{ bet.league }}</div>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <span class="font-bold text-green-600">{{ bet.best_odds.toFixed(2) }}</span>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <span class="bg-green-100 text-green-800 px-2 py-1 rounded text-sm font-medium">
                                        +{{ bet.edge_percent.toFixed(1) }}%
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <span :class="{
                                        'bg-yellow-100 text-yellow-800': bet.status === 'pending',
                                        'bg-green-100 text-green-800': bet.status === 'won',
                                        'bg-red-100 text-red-800': bet.status === 'lost',
                                        'bg-gray-100 text-gray-800': bet.status === 'push' || bet.status === 'void'
                                    }" class="px-2 py-1 rounded text-sm font-medium uppercase">
                                        {{ bet.status }}
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <span v-if="bet.profit !== null" :class="bet.profit >= 0 ? 'text-green-600' : 'text-red-600'" class="font-bold">
                                        {{ bet.profit >= 0 ? '+' : '' }}{{ bet.profit.toFixed(2) }}
                                    </span>
                                    <span v-else class="text-gray-400">-</span>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Settings Tab -->
            <div v-if="currentTab === 'settings'">
                <h2 class="text-2xl font-bold text-gray-800 mb-6">Settings</h2>
                <div class="bg-white rounded-lg shadow p-6">
                    <form @submit.prevent="saveSettings" class="space-y-6">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Minimum Edge (%)
                            </label>
                            <input type="number" v-model="settings.min_edge_percent" step="0.5" min="0"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Refresh Interval (minutes)
                            </label>
                            <input type="number" v-model="settings.refresh_interval_minutes" min="1" max="60"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Hours Ahead
                            </label>
                            <input type="number" v-model="settings.hours_ahead" min="1" max="72"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Telegram Bot Token
                            </label>
                            <input type="text" v-model="settings.telegram.bot_token" placeholder="Enter bot token"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Telegram Chat ID
                            </label>
                            <input type="text" v-model="settings.telegram.chat_id" placeholder="Enter chat ID"
                                   class="w-full border rounded px-3 py-2 focus:ring-green-500 focus:border-green-500">
                        </div>

                        <button type="submit"
                                class="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700">
                            Save Settings
                        </button>
                    </form>
                </div>
            </div>
        </main>

        <footer class="text-center text-gray-500 py-4 mt-8">
            <p>Soccer Props Value Betting System v1.0</p>
        </footer>
    </div>

    <script>
        const { createApp, ref, computed, onMounted } = Vue

        createApp({
            setup() {
                const currentTab = ref('bets')
                const loading = ref(false)
                const valueBets = ref([])
                const fixtures = ref([])
                const settings = ref({
                    min_edge_percent: 5.0,
                    refresh_interval_minutes: 3,
                    hours_ahead: 24,
                    telegram: {
                        bot_token: '',
                        chat_id: ''
                    }
                })
                const filters = ref({
                    minEdge: 0,
                    minOdds: null,
                    maxOdds: null,
                    market: '',
                    book: ''
                })
                const trackingStats = ref({
                    total_bets: 0,
                    pending: 0,
                    settled: 0,
                    won: 0,
                    lost: 0,
                    pushed: 0,
                    win_rate: 0,
                    total_profit: 0,
                    total_staked: 0,
                    roi: 0,
                    avg_odds_won: 0,
                    avg_edge: 0
                })
                const trackedBets = ref([])

                const filteredBets = computed(() => {
                    return valueBets.value.filter(bet => {
                        if (filters.value.minEdge > 0 && bet.edge_percent < filters.value.minEdge) {
                            return false
                        }
                        if (filters.value.minOdds && bet.best_odds < filters.value.minOdds) {
                            return false
                        }
                        if (filters.value.maxOdds && bet.best_odds > filters.value.maxOdds) {
                            return false
                        }
                        if (filters.value.market && bet.market !== filters.value.market) {
                            return false
                        }
                        if (filters.value.book && bet.best_book !== filters.value.book) {
                            return false
                        }
                        return true
                    })
                })

                const resetFilters = () => {
                    filters.value = { minEdge: 0, minOdds: null, maxOdds: null, market: '', book: '' }
                }

                const fetchValueBets = async () => {
                    loading.value = true
                    try {
                        const response = await fetch('/api/value-bets')
                        valueBets.value = await response.json()
                    } catch (error) {
                        console.error('Failed to fetch value bets:', error)
                    } finally {
                        loading.value = false
                    }
                }

                const fetchFixtures = async () => {
                    try {
                        const response = await fetch('/api/fixtures')
                        fixtures.value = await response.json()
                    } catch (error) {
                        console.error('Failed to fetch fixtures:', error)
                    }
                }

                const fetchSettings = async () => {
                    try {
                        const response = await fetch('/api/settings')
                        settings.value = await response.json()
                    } catch (error) {
                        console.error('Failed to fetch settings:', error)
                    }
                }

                const saveSettings = async () => {
                    try {
                        const response = await fetch('/api/settings', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(settings.value)
                        })
                        if (response.ok) {
                            alert('Settings saved!')
                        }
                    } catch (error) {
                        console.error('Failed to save settings:', error)
                        alert('Failed to save settings')
                    }
                }

                const formatDate = (dateStr) => {
                    if (!dateStr) return 'TBD'
                    const date = new Date(dateStr)
                    return date.toLocaleString()
                }

                const fetchTrackingData = async () => {
                    try {
                        const [statsRes, betsRes] = await Promise.all([
                            fetch('/api/tracking/stats'),
                            fetch('/api/tracking/bets?limit=50')
                        ])
                        trackingStats.value = await statsRes.json()
                        trackedBets.value = await betsRes.json()
                    } catch (error) {
                        console.error('Failed to fetch tracking data:', error)
                    }
                }

                const logBetsForTracking = async () => {
                    try {
                        const response = await fetch('/api/tracking/log?min_edge=10.0&max_bets=20', {
                            method: 'POST'
                        })
                        const result = await response.json()
                        alert(`Logged ${result.logged} new bets for tracking`)
                        fetchTrackingData()
                    } catch (error) {
                        console.error('Failed to log bets:', error)
                        alert('Failed to log bets')
                    }
                }

                const checkResults = async () => {
                    try {
                        const response = await fetch('/api/tracking/check-results', {
                            method: 'POST'
                        })
                        const result = await response.json()
                        alert(`Checked ${result.checked} fixtures, settled ${result.settled} bets`)
                        fetchTrackingData()
                    } catch (error) {
                        console.error('Failed to check results:', error)
                        alert('Failed to check results')
                    }
                }

                onMounted(() => {
                    fetchValueBets()
                    fetchFixtures()
                    fetchSettings()
                    fetchTrackingData()

                    // Auto-refresh every 30 seconds
                    setInterval(fetchValueBets, 30000)
                    setInterval(fetchTrackingData, 60000)
                })

                return {
                    currentTab,
                    loading,
                    valueBets,
                    filteredBets,
                    fixtures,
                    settings,
                    filters,
                    trackingStats,
                    trackedBets,
                    fetchValueBets,
                    saveSettings,
                    resetFilters,
                    formatDate,
                    fetchTrackingData,
                    logBetsForTracking,
                    checkResults
                }
            }
        }).mount('#app')
    </script>
</body>
</html>
"""
