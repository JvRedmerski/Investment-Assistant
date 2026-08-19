import { useEffect, useState } from 'react';
import { fetchHealth, HealthResponse } from './services/api';
import { 
  TrendingUp, 
  ShieldCheck, 
  PieChart, 
  Zap, 
  Cpu, 
  Activity,
  ArrowUpRight,
  Sparkles
} from 'lucide-react';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-sky-500/10 border border-sky-500/30 p-2 rounded-xl text-sky-400">
              <TrendingUp className="w-6 h-6" />
            </div>
            <div>
              <h1 className="font-bold text-lg text-white leading-none">Investment Assistant</h1>
              <span className="text-xs text-slate-400 font-medium">Análise Quantitativa & IA — B3</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700">
              <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
              <span className="text-slate-300 font-medium">
                {loading ? 'Verificando backend...' : error ? 'Backend Offline (Modo Local)' : `Backend v${health?.version}`}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        {/* Banner Welcome & Portfolio Overview */}
        <section className="relative overflow-hidden rounded-2xl glass-card p-6 md:p-8 bg-gradient-to-br from-slate-900 via-slate-900/90 to-sky-950/40 border border-slate-800">
          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs font-semibold uppercase tracking-wider">
                <Sparkles className="w-3.5 h-3.5" /> Wave 01 — Foundation Ativa
              </div>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-white">
                Plataforma Pessoal de Inteligência Financeira
              </h2>
              <p className="text-slate-400 text-sm leading-relaxed">
                Análise determinística de carteiras, motor quantitativo de alocação de novos aportes, restrições para perfil conservador e monitoramento intraday de Day Trade com Paper Trading.
              </p>
            </div>
          </div>
        </section>

        {/* Status Indicators Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="glass-card p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider">Patrimônio Atual</span>
              <PieChart className="w-4 h-4 text-sky-400" />
            </div>
            <div className="text-2xl font-bold text-white">R$ 0,00</div>
            <div className="mt-2 text-xs text-slate-400 flex items-center gap-1">
              <span>Posições derivadas de transações</span>
            </div>
          </div>

          <div className="glass-card p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider">Aporte Mensal Alvo</span>
              <ArrowUpRight className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-white">R$ 1.000,00</div>
            <div className="mt-2 text-xs text-emerald-400 font-medium">
              Alocação Otimizada Quant Engine
            </div>
          </div>

          <div className="glass-card p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider">Perfil de Risco</span>
              <ShieldCheck className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-2xl font-bold text-white">Conservador</div>
            <div className="mt-2 text-xs text-slate-400">
              Restrições ativas de concentração
            </div>
          </div>

          <div className="glass-card p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider">Módulo Day Trade</span>
              <Zap className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold text-white">Paper Trading</div>
            <div className="mt-2 text-xs text-amber-400/90 font-medium">
              Setups: Breakout / Pullback / VWAP
            </div>
          </div>
        </div>

        {/* Modules Overview Architecture */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Cpu className="w-5 h-5 text-sky-400" /> Domínios da Arquitetura (AGENTS.md)
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="glass-card p-6 rounded-xl space-y-3">
              <div className="bg-sky-500/10 text-sky-400 w-10 h-10 rounded-lg flex items-center justify-center font-bold">
                01
              </div>
              <h4 className="font-bold text-white text-base">Quant Engine</h4>
              <p className="text-slate-400 text-xs leading-relaxed">
                Cálculos determinísticos de rentabilidade (CAGR, YTD), volatilidade, Beta, Sharpe, Sortino e Max Drawdown no Backend.
              </p>
            </div>

            <div className="glass-card p-6 rounded-xl space-y-3">
              <div className="bg-emerald-500/10 text-emerald-400 w-10 h-10 rounded-lg flex items-center justify-center font-bold">
                02
              </div>
              <h4 className="font-bold text-white text-base">Recommendation Engine</h4>
              <p className="text-slate-400 text-xs leading-relaxed">
                Avaliação de scores (Quality, Valuation, Growth, Risk, Portfolio Fit) para determinar onde cada aporte melhora a carteira.
              </p>
            </div>

            <div className="glass-card p-6 rounded-xl space-y-3">
              <div className="bg-indigo-500/10 text-indigo-400 w-10 h-10 rounded-lg flex items-center justify-center font-bold">
                03
              </div>
              <h4 className="font-bold text-white text-base">AI Engine (Explicabilidade)</h4>
              <p className="text-slate-400 text-xs leading-relaxed">
                Interpretação e explicações em linguagem natural com Gemini / Ollama sobre os dados quantitativos reais gerados pelo sistema.
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-950 py-6 mt-auto">
        <div className="max-w-7xl mx-auto px-4 text-center text-xs text-slate-500">
          Investment Assistant — Sistema de Análise e Pesquisa Financeira | Desenvolvido com base no AGENTS.md e roadmap.md
        </div>
      </footer>
    </div>
  );
}

export default App;
