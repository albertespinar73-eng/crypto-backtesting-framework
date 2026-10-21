//+------------------------------------------------------------------+
//| DAX40_AsianSweep_EA.mq5                                          |
//|                                                                    |
//| Puerto a MQL5 del motor de detección en dax_model/ (Python) --     |
//| ver docs/STRATEGY_SPEC.md para la especificación completa.         |
//|                                                                    |
//| ALCANCE (igual que dax_model/detector.py):                         |
//|  - Solo el Modelo Primario (barrido de Asian High/Low). Los         |
//|    modelos Alternativo (liquidez interna) y de Continuación NO      |
//|    están implementados todavía.                                     |
//|  - Take-profit fijo RR 1:2 -- la extensión hacia PDH/PDL/liquidez    |
//|    de HTF no está implementada.                                      |
//|  - La mitigación de FVGs se evalúa en un único punto (cierre del     |
//|    MSS, o inicio de killzone si el MSS se confirmó antes) -- no una  |
//|    simulación vela a vela.                                            |
//|                                                                        |
//| SIN COMPILAR: este archivo se ha escrito sin acceso a MetaEditor/     |
//| compilador MQL5. Compílalo (F7) antes de usarlo y reporta cualquier   |
//| error para corregirlo.                                                 |
//|                                                                          |
//| NUNCA lo conectes a una cuenta real sin pasar antes por demo (ver       |
//| docs/DEPLOYMENT_PLAN.md) y sin confirmar los parámetros de la sección   |
//| "Preguntas abiertas" de más abajo contra tu bróker/cuenta real.          |
//+------------------------------------------------------------------+
#property copyright "DAX40 Asian-Sweep model"
#property strict
#property version   "0.1"

#include <Trade\Trade.mqh>
CTrade trade;

//====================================================================
// INPUTS
//====================================================================

input group "=== Preguntas abiertas -- AJUSTAR antes de usar (ver docs/OPEN_QUESTIONS.md) ==="
input int    InpBrokerToCETOffsetHours = 0;     // Horas a SUMAR a la hora del bróker para obtener CET (pregunta #1)
input double InpPointValuePerLot       = 1.0;   // Valor de 1 punto por 1.0 lote, en divisa de la cuenta (pregunta #2) -- si se deja en 0, se calcula desde SYMBOL_TRADE_TICK_VALUE

input group "=== Sesión asiática / Killzone (Sección 2 del brief) ==="
input int  InpAsianOpenHour       = 23;   // Apertura nocturna del CFD, hora CET (pregunta #1)
input int  InpAsianOpenMinute     = 0;
input int  InpKillzoneStartHour   = 8;    // Fijado por Albert
input int  InpKillzoneStartMinute = 15;
input int  InpKillzoneEndHour     = 10;
input int  InpKillzoneEndMinute   = 45;
input int  InpMssMinHour          = 8;    // CONFIRMADO por Albert (pregunta #5): el MSS solo cuenta dentro de
input int  InpMssMinMinute        = 0;    // esta ventana CET (08:00-10:30 por defecto), independiente de la
input int  InpMssMaxHour          = 10;   // killzone de ejecución (08:15-10:45) -- tanto el sweep como el MSS
input int  InpMssMaxMinute        = 30;   // deben ocurrir DESPUES del cierre del rango asiático.

input group "=== Estructura / MSS ==="
input int InpPivotLeft  = 1;
input int InpPivotRight = 1;

input group "=== Entrada / Riesgo (Sección 5) ==="
input double InpMaxSLPoints   = 75.0;  // CALIBRADO contra Full_Backtest.numbers (ver docs/OPEN_QUESTIONS.md #4bis)
input double InpRiskPercent   = 1.0;   // % de equity arriesgado por operación, SIEMPRE fijo
input double InpTakeProfitRR  = 2.0;

input group "=== Límites diarios (Sección 5) ==="
input int  InpMaxTradesPerDay    = 2;
input bool InpStopAfterFirstLoss = true;

input group "=== Kill-switch de drawdown (Sección 5) -- PLACEHOLDER, confirmar con la prop firm (pregunta #3) ==="
input double InpDailyDrawdownLimitPct = 5.0;
input double InpTotalDrawdownLimitPct = 10.0;
input double InpDrawdownWarningPct    = 80.0;  // % del propio límite, no del equity

input group "=== Filtro de estructura 15m (Sección 3, CONFIRMADO activo por Albert) ==="
input bool InpM15FilterEnabled  = true;
input bool InpM15FilterSkipMode = true;  // true = descartar operación; false = tomarla con tamaño reducido

input group "=== Filtro de estructura 1H (NUEVO, desactivado por defecto -- ver docs/OPEN_QUESTIONS.md #11) ==="
input bool InpH1FilterEnabled = false;

input group "=== Filtro de tendencia SMA100 (NUEVO, sin validar -- ver docs/OPEN_QUESTIONS.md #12) ==="
input bool             InpMATrendFilterEnabled = false;
input int               InpMATrendPeriod        = 100;
input ENUM_TIMEFRAMES   InpMATrendTimeframe      = PERIOD_H1;  // solo PERIOD_H1 o PERIOD_M15

input group "=== Breakeven (Sección 2) ==="
input bool   InpBreakevenEnabled = true;
input double InpBreakevenMinR    = 1.0;

input group "=== Otros ==="
input long InpMagicNumber = 40401;

//====================================================================
// CONSTANTES / TIPOS
//====================================================================

#define BIAS_NONE   0
#define BIAS_LONG   1
#define BIAS_SHORT -1

#define SWING_HH 0
#define SWING_HL 1
#define SWING_LH 2
#define SWING_LL 3

#define LOOKBACK_M5  400   // ~ cubre sesión asiática + killzone con margen
#define LOOKBACK_M15 200
#define LOOKBACK_H1  150

struct SwingPoint
{
   int      index;
   datetime time;
   double   price;
   bool     isHigh;
   int      kind;
};

struct FvgZone
{
   bool     bearish;
   int      c1, c2, c3;
   double   top, bottom;
   datetime formedAt;
};

struct EntryResult
{
   bool    valid;
   double  price;
   double  stopLoss;
   double  stopDistance;
   int     fvgRank;
   FvgZone fvg;
};

struct FilterResult
{
   bool   takeTrade;
   int    alignedState; // 0 = filtro apagado / desconocido, 1 = alineado, 2 = en contra
};

struct SetupResult
{
   bool        found;
   bool        taken;
   string      discardReason;
   int         direction;
   int         sweepIndex;
   double      sweepPrice;
   int         mssIndex;
   double      refLevel;
   EntryResult entry;
   double      takeProfit;
};

enum DrawdownState { DD_ACTIVE, DD_WARNING, DD_HALTED };

//====================================================================
// ESTADO GLOBAL
//====================================================================

datetime g_lastM5BarTime   = 0;
datetime g_currentDayDate  = 0;
int      g_tradesToday     = 0;
bool     g_stoppedForDay   = false;
double   g_dayStartEquity  = 0;
double   g_accountStartEquity = 0;
double   g_positionRefLevel = 0;
bool     g_haltedByKillSwitch = false;

//====================================================================
// SESIONES / TIEMPO
//====================================================================

datetime BrokerTimeToCET(datetime brokerTime)
{
   return brokerTime + InpBrokerToCETOffsetHours * 3600;
}

int MinutesOfDay(datetime t)
{
   MqlDateTime s;
   TimeToStruct(t, s);
   return s.hour * 60 + s.min;
}

bool InWindow(int minutesOfDay, int startH, int startM, int endH, int endM)
{
   int start = startH * 60 + startM;
   int end   = endH * 60 + endM;
   if(start <= end)
      return (minutesOfDay >= start && minutesOfDay < end);
   return (minutesOfDay >= start || minutesOfDay < end);
}

bool InKillzone(datetime cetTime)
{
   int m     = MinutesOfDay(cetTime);
   int start = InpKillzoneStartHour * 60 + InpKillzoneStartMinute;
   int end   = InpKillzoneEndHour * 60 + InpKillzoneEndMinute;
   if(start <= end)
      return (m >= start && m <= end);
   return (m >= start || m <= end);
}

int IndexAtOrBefore(const MqlRates &rates[], int n, datetime target)
{
   int idx = -1;
   for(int i = 0; i < n; i++)
   {
      if(rates[i].time <= target) idx = i;
      else break;
   }
   return idx;
}

int IndexAtOrBeforeKillzoneStart(const MqlRates &rates[], int n, datetime mssBrokerTime)
{
   datetime mssCET = BrokerTimeToCET(mssBrokerTime);
   MqlDateTime s;
   TimeToStruct(mssCET, s);
   s.hour = InpKillzoneStartHour;
   s.min  = InpKillzoneStartMinute;
   s.sec  = 0;
   datetime killzoneStartCET    = StructToTime(s);
   datetime killzoneStartBroker = killzoneStartCET - InpBrokerToCETOffsetHours * 3600;
   return IndexAtOrBefore(rates, n, killzoneStartBroker);
}

// Busca el ÚLTIMO tramo contiguo de velas dentro de la ventana asiática
// (apertura nocturna -> 06:00 CET) presente en el lookback dado.
bool ComputeAsianRange(const MqlRates &rates[], int n, double &outHigh, double &outLow, int &outEndIndex)
{
   int lastStart = -1, lastEnd = -1, curStart = -1;
   for(int i = 0; i < n; i++)
   {
      datetime cet = BrokerTimeToCET(rates[i].time);
      bool inWin = InWindow(MinutesOfDay(cet), InpAsianOpenHour, InpAsianOpenMinute, 6, 0);
      if(inWin)
      {
         if(curStart == -1) curStart = i;
      }
      else
      {
         if(curStart != -1) { lastStart = curStart; lastEnd = i; curStart = -1; }
      }
   }
   if(curStart != -1) { lastStart = curStart; lastEnd = n; }
   if(lastStart == -1) return false;

   double h = -DBL_MAX, l = DBL_MAX;
   for(int i = lastStart; i < lastEnd; i++)
   {
      if(rates[i].high > h) h = rates[i].high;
      if(rates[i].low  < l) l = rates[i].low;
   }
   outHigh = h;
   outLow  = l;
   outEndIndex = lastEnd;
   return true;
}

//====================================================================
// ESTRUCTURA / MSS (dax_model/structure.py)
//====================================================================

void FindPivots(const MqlRates &rates[], int n, int left, int right, SwingPoint &pivots[])
{
   ArrayResize(pivots, 0);
   for(int i = left; i < n - right; i++)
   {
      double h = rates[i].high;
      double l = rates[i].low;

      bool isHigh = true;
      for(int k = 1; k <= left && isHigh; k++)  if(rates[i - k].high >= h) isHigh = false;
      for(int k = 1; k <= right && isHigh; k++) if(rates[i + k].high >= h) isHigh = false;

      bool isLow = true;
      for(int k = 1; k <= left && isLow; k++)  if(rates[i - k].low <= l) isLow = false;
      for(int k = 1; k <= right && isLow; k++) if(rates[i + k].low <= l) isLow = false;

      if(isHigh)
      {
         int sz = ArraySize(pivots);
         ArrayResize(pivots, sz + 1);
         pivots[sz].index = i; pivots[sz].time = rates[i].time; pivots[sz].price = h;
         pivots[sz].isHigh = true; pivots[sz].kind = -1;
      }
      if(isLow)
      {
         int sz = ArraySize(pivots);
         ArrayResize(pivots, sz + 1);
         pivots[sz].index = i; pivots[sz].time = rates[i].time; pivots[sz].price = l;
         pivots[sz].isHigh = false; pivots[sz].kind = -1;
      }
   }
}

void ClassifySwings(SwingPoint &pivots[])
{
   double lastHigh = 0; bool haveHigh = false;
   double lastLow  = 0; bool haveLow  = false;
   int n = ArraySize(pivots);
   for(int i = 0; i < n; i++)
   {
      if(pivots[i].isHigh)
      {
         pivots[i].kind = (!haveHigh || pivots[i].price > lastHigh) ? SWING_HH : SWING_LH;
         lastHigh = pivots[i].price; haveHigh = true;
      }
      else
      {
         pivots[i].kind = (!haveLow || pivots[i].price > lastLow) ? SWING_HL : SWING_LL;
         lastLow = pivots[i].price; haveLow = true;
      }
   }
}

bool LastSwingBefore(const SwingPoint &pivots[], int kind, int beforeIndex, SwingPoint &result)
{
   bool found = false;
   int bestIdx = -1;
   int n = ArraySize(pivots);
   for(int i = 0; i < n; i++)
   {
      if(pivots[i].kind == kind && pivots[i].index < beforeIndex)
      {
         if(!found || pivots[i].index > bestIdx)
         {
            found = true; bestIdx = pivots[i].index; result = pivots[i];
         }
      }
   }
   return found;
}

int DetectMSS(const MqlRates &rates[], int n, double referenceLevel, bool isShort, int searchStart, int searchEndExclusive)
{
   int end = (searchEndExclusive < 0) ? n : searchEndExclusive;
   for(int i = searchStart; i < end; i++)
   {
      double c = rates[i].close;
      if(isShort  && c < referenceLevel) return i;
      if(!isShort && c > referenceLevel) return i;
   }
   return -1;
}

// Sesgo de estructura genérico (reutilizado para 15m y 1H, igual que
// dax_model/htf_filter.py::compute_m15_bias).
int ComputeStructureBias(const MqlRates &rates[], int n, int left, int right)
{
   if(n <= 0) return BIAS_NONE;

   SwingPoint pivots[];
   FindPivots(rates, n, left, right, pivots);
   ClassifySwings(pivots);

   int m = ArraySize(pivots);
   for(int a = 1; a < m; a++)
   {
      SwingPoint key = pivots[a];
      int keyConfirm = key.index + right;
      int b = a - 1;
      while(b >= 0 && (pivots[b].index + right) > keyConfirm)
      {
         pivots[b + 1] = pivots[b];
         b--;
      }
      pivots[b + 1] = key;
   }

   int bias = BIAS_NONE;
   double lastHigh = 0; bool haveHigh = false;
   double lastLow  = 0; bool haveLow  = false;
   int ptr = 0;
   for(int i = 0; i < n; i++)
   {
      while(ptr < m && (pivots[ptr].index + right) <= i)
      {
         if(pivots[ptr].isHigh) { lastHigh = pivots[ptr].price; haveHigh = true; }
         else                   { lastLow  = pivots[ptr].price; haveLow  = true; }
         ptr++;
      }
      if(haveHigh && rates[i].close > lastHigh) bias = BIAS_LONG;
      if(haveLow  && rates[i].close < lastLow)  bias = BIAS_SHORT;
   }
   return bias;
}

//====================================================================
// FVG (dax_model/fvg.py)
//====================================================================

void FindFvgs(const MqlRates &rates[], int startIndex, int endIndexExclusive, FvgZone &fvgs[])
{
   ArrayResize(fvgs, 0);
   for(int i = startIndex; i < endIndexExclusive - 2; i++)
   {
      double c1low = rates[i].low, c1high = rates[i].high;
      double c3low = rates[i + 2].low, c3high = rates[i + 2].high;

      if(c1low > c3high)
      {
         int sz = ArraySize(fvgs);
         ArrayResize(fvgs, sz + 1);
         fvgs[sz].bearish = true; fvgs[sz].c1 = i; fvgs[sz].c2 = i + 1; fvgs[sz].c3 = i + 2;
         fvgs[sz].top = c1low; fvgs[sz].bottom = c3high; fvgs[sz].formedAt = rates[i + 2].time;
      }
      else if(c1high < c3low)
      {
         int sz = ArraySize(fvgs);
         ArrayResize(fvgs, sz + 1);
         fvgs[sz].bearish = false; fvgs[sz].c1 = i; fvgs[sz].c2 = i + 1; fvgs[sz].c3 = i + 2;
         fvgs[sz].top = c3low; fvgs[sz].bottom = c1high; fvgs[sz].formedAt = rates[i + 2].time;
      }
   }
}

bool IsMitigated(const MqlRates &rates[], const FvgZone &fvg, int upToIndexExclusive, bool fullFill)
{
   int start = fvg.c3 + 1;
   int limit = MathMin(upToIndexExclusive, ArraySize(rates));
   for(int i = start; i < limit; i++)
   {
      if(fullFill)
      {
         if(rates[i].low <= fvg.bottom && rates[i].high >= fvg.top) return true;
      }
      else
      {
         if(rates[i].high >= fvg.bottom && rates[i].low <= fvg.top) return true;
      }
   }
   return false;
}

double FvgNearEdge(const FvgZone &fvg, double origin)
{
   double dTop = MathAbs(origin - fvg.top);
   double dBot = MathAbs(origin - fvg.bottom);
   return (dTop <= dBot) ? fvg.top : fvg.bottom;
}

//====================================================================
// ENTRADA / SL (dax_model/entry.py)
//====================================================================

bool ChooseEntry(const FvgZone &fvgsIn[], double origin, double maxSlPoints, EntryResult &result)
{
   int n = ArraySize(fvgsIn);
   int order[];
   ArrayResize(order, n);
   for(int i = 0; i < n; i++) order[i] = i;

   // orden por distancia del borde más cercano al origen, DESCENDENTE
   // (el FVG más cercano al precio actual se intenta primero)
   for(int a = 0; a < n - 1; a++)
   {
      for(int b = 0; b < n - 1 - a; b++)
      {
         double d1 = MathAbs(origin - FvgNearEdge(fvgsIn[order[b]], origin));
         double d2 = MathAbs(origin - FvgNearEdge(fvgsIn[order[b + 1]], origin));
         if(d1 < d2)
         {
            int tmp = order[b]; order[b] = order[b + 1]; order[b + 1] = tmp;
         }
      }
   }

   for(int rank = 0; rank < n; rank++)
   {
      FvgZone f = fvgsIn[order[rank]];
      double near = FvgNearEdge(f, origin);
      double dist = MathAbs(origin - near);
      if(dist <= maxSlPoints)
      {
         result.valid = true; result.price = near; result.stopLoss = origin;
         result.stopDistance = dist; result.fvgRank = rank; result.fvg = f;
         return true;
      }
   }
   result.valid = false;
   return false;
}

//====================================================================
// FILTROS DE ESTRUCTURA (15m / 1H) Y SMA100 (dax_model/htf_filter.py, trend_filter.py)
//====================================================================

FilterResult EvaluateStructureFilter(int direction, int bias, bool enabled, bool skipMode)
{
   FilterResult r;
   if(!enabled) { r.takeTrade = true; r.alignedState = 0; return r; }

   bool aligned = (bias != BIAS_NONE && bias == direction);
   if(aligned) { r.takeTrade = true; r.alignedState = 1; return r; }

   r.alignedState = 2;
   r.takeTrade = !skipMode; // skipMode=true -> descartar; false -> tomar igualmente (tamaño reducido se gestiona en el sizing, no aquí)
   return r;
}

FilterResult EvaluateMATrendFilter(int direction, int bias, bool enabled)
{
   FilterResult r;
   if(!enabled) { r.takeTrade = true; r.alignedState = 0; return r; }
   bool aligned = (bias != BIAS_NONE && bias == direction);
   r.alignedState = aligned ? 1 : 2;
   r.takeTrade = aligned;
   return r;
}

int ComputeMATrendBias(const MqlRates &rates[], int n, int period)
{
   if(n < period) return BIAS_NONE;
   double sum = 0;
   for(int i = n - period; i < n; i++) sum += rates[i].close;
   double ma = sum / period;
   double lastClose = rates[n - 1].close;
   if(lastClose > ma) return BIAS_LONG;
   if(lastClose < ma) return BIAS_SHORT;
   return BIAS_NONE;
}

//====================================================================
// RIESGO (dax_model/risk.py)
//====================================================================

double CalcMoneyPerPointPerLot(string symbol)
{
   if(InpPointValuePerLot > 0) return InpPointValuePerLot;
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double point     = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(tickSize <= 0) return 0;
   return tickValue / tickSize * point;
}

double CalcPositionSizeLots(string symbol, double equity, double riskPct, double stopPoints)
{
   double moneyPerPoint = CalcMoneyPerPointPerLot(symbol);
   if(moneyPerPoint <= 0 || stopPoints <= 0) return 0;

   double riskMoney = equity * riskPct / 100.0;
   double lots = riskMoney / (stopPoints * moneyPerPoint);

   double volStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double volMin  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double volMax  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(volStep > 0) lots = MathFloor(lots / volStep) * volStep;
   if(lots < volMin) return 0; // no se puede respetar el 1% de riesgo con el lote mínimo -> no operar
   if(lots > volMax) lots = volMax;
   return lots;
}

void ResetDailyLimiterIfNewDay(datetime brokerTime)
{
   MqlDateTime dt;
   TimeToStruct(brokerTime, dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime today = StructToTime(dt);
   if(today != g_currentDayDate)
   {
      g_currentDayDate = today;
      g_tradesToday = 0;
      g_stoppedForDay = false;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   }
}

bool CanTrade()
{
   return (!g_stoppedForDay && g_tradesToday < InpMaxTradesPerDay && !g_haltedByKillSwitch);
}

void InitDrawdownGuardrail()
{
   string gvName = "DAX40_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "_AccountStartEquity";
   if(GlobalVariableCheck(gvName))
      g_accountStartEquity = GlobalVariableGet(gvName);
   else
   {
      g_accountStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      GlobalVariableSet(gvName, g_accountStartEquity);
   }
}

DrawdownState EvaluateDrawdown(double currentEquity)
{
   if(g_dayStartEquity <= 0 || g_accountStartEquity <= 0) return DD_ACTIVE;
   double dailyDD = MathMax(0.0, (g_dayStartEquity - currentEquity) / g_dayStartEquity);
   double totalDD = MathMax(0.0, (g_accountStartEquity - currentEquity) / g_accountStartEquity);
   double dailyRatio = dailyDD / (InpDailyDrawdownLimitPct / 100.0);
   double totalRatio = totalDD / (InpTotalDrawdownLimitPct / 100.0);
   double worst = MathMax(dailyRatio, totalRatio);
   if(worst >= 1.0) return DD_HALTED;
   if(worst >= (InpDrawdownWarningPct / 100.0)) return DD_WARNING;
   return DD_ACTIVE;
}

void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      trade.PositionClose(ticket);
   }
}

//====================================================================
// ORQUESTADOR (dax_model/detector.py)
//====================================================================

bool EvaluateDirection(const MqlRates &m5[], int n5, const MqlRates &m15[], int n15,
                        const MqlRates &h1[], int n1h, double asianHigh, double asianLow,
                        int monitorStart, int direction, SetupResult &out)
{
   out.found = false; out.taken = false; out.direction = direction;
   bool isShort = (direction == BIAS_SHORT);
   double sweepLevel = isShort ? asianHigh : asianLow;

   int sweepIndex = -1;
   for(int i = monitorStart; i < n5; i++)
   {
      if(isShort  && m5[i].high > sweepLevel) { sweepIndex = i; break; }
      if(!isShort && m5[i].low  < sweepLevel) { sweepIndex = i; break; }
   }
   if(sweepIndex == -1) return false;

   SwingPoint pivots[];
   FindPivots(m5, sweepIndex + 1, InpPivotLeft, InpPivotRight, pivots);
   ClassifySwings(pivots);
   int refKind = isShort ? SWING_HL : SWING_LH;
   SwingPoint refSwing;
   bool haveRef = LastSwingBefore(pivots, refKind, sweepIndex, refSwing);
   if(!haveRef)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "NO_REFERENCE_SWING";
      return true;
   }

   int mssIndex = DetectMSS(m5, n5, refSwing.price, isShort, sweepIndex + 1, -1);
   if(mssIndex == -1) return false; // MSS todavía no confirmado con los datos disponibles

   datetime mssTimeCET = BrokerTimeToCET(m5[mssIndex].time);
   bool mssInKillzone = InKillzone(mssTimeCET);

   MqlDateTime mssStruct; TimeToStruct(mssTimeCET, mssStruct);
   int mssMinutesOfDay = mssStruct.hour * 60 + mssStruct.min;
   int mssMinMinutesOfDay = InpMssMinHour * 60 + InpMssMinMinute;
   if(mssMinutesOfDay < mssMinMinutesOfDay)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "MSS_TOO_EARLY";
      return true;
   }

   int mssMaxMinutesOfDay = InpMssMaxHour * 60 + InpMssMaxMinute;
   if(mssMinutesOfDay > mssMaxMinutesOfDay)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "MSS_TOO_LATE";
      return true;
   }

   double origin = isShort ? m5[sweepIndex].high : m5[sweepIndex].low;

   FvgZone fvgs[];
   FindFvgs(m5, sweepIndex, mssIndex + 1, fvgs);
   if(ArraySize(fvgs) == 0)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "NO_FVG";
      return true;
   }

   int mitigationCheckIndex = mssInKillzone ? (mssIndex + 1) : IndexAtOrBeforeKillzoneStart(m5, n5, m5[mssIndex].time);

   FvgZone unmitigated[];
   ArrayResize(unmitigated, 0);
   for(int i = 0; i < ArraySize(fvgs); i++)
   {
      if(!IsMitigated(m5, fvgs[i], mitigationCheckIndex, true))
      {
         int sz = ArraySize(unmitigated);
         ArrayResize(unmitigated, sz + 1);
         unmitigated[sz] = fvgs[i];
      }
   }
   if(ArraySize(unmitigated) == 0)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "ALL_FVG_MITIGATED";
      return true;
   }

   EntryResult entry;
   bool gotEntry = ChooseEntry(unmitigated, origin, InpMaxSLPoints, entry);
   if(!gotEntry)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "SL_EXCEEDS_MAX";
      return true;
   }

   double takeProfit = isShort ? (entry.price - entry.stopDistance * InpTakeProfitRR)
                                : (entry.price + entry.stopDistance * InpTakeProfitRR);

   int idx15 = (n15 > 0) ? IndexAtOrBefore(m15, n15, m5[mssIndex].time) : -1;
   int m15Bias = (idx15 >= 0) ? ComputeStructureBias(m15, idx15 + 1, InpPivotLeft, InpPivotRight) : BIAS_NONE;
   FilterResult m15Result = EvaluateStructureFilter(direction, m15Bias, InpM15FilterEnabled, InpM15FilterSkipMode);
   if(!m15Result.takeTrade)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "M15_MISALIGNED";
      return true;
   }

   int idx1h = (n1h > 0) ? IndexAtOrBefore(h1, n1h, m5[mssIndex].time) : -1;
   int h1Bias = (idx1h >= 0) ? ComputeStructureBias(h1, idx1h + 1, InpPivotLeft, InpPivotRight) : BIAS_NONE;
   FilterResult h1Result = EvaluateStructureFilter(direction, h1Bias, InpH1FilterEnabled, true);
   if(!h1Result.takeTrade)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "H1_MISALIGNED";
      return true;
   }

   int maBias = BIAS_NONE;
   if(InpMATrendFilterEnabled)
   {
      if(InpMATrendTimeframe == PERIOD_H1 && idx1h >= 0)
         maBias = ComputeMATrendBias(h1, idx1h + 1, InpMATrendPeriod);
      else if(idx15 >= 0)
         maBias = ComputeMATrendBias(m15, idx15 + 1, InpMATrendPeriod);
   }
   FilterResult maResult = EvaluateMATrendFilter(direction, maBias, InpMATrendFilterEnabled);
   if(!maResult.takeTrade)
   {
      out.found = true; out.taken = false; out.sweepIndex = sweepIndex;
      out.discardReason = "MA100_TREND_MISALIGNED";
      return true;
   }

   out.found = true; out.taken = true; out.sweepIndex = sweepIndex; out.sweepPrice = sweepLevel;
   out.mssIndex = mssIndex; out.refLevel = refSwing.price; out.entry = entry; out.takeProfit = takeProfit;
   return true;
}

void OpenTradeFromSetup(const SetupResult &res)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double lots = CalcPositionSizeLots(_Symbol, equity, InpRiskPercent, res.entry.stopDistance);
   if(lots <= 0)
   {
      Print("Tamaño de posición no calculable (lote mínimo del símbolo > riesgo permitido) -- operación NO ejecutada");
      return;
   }

   bool isShort = (res.direction == BIAS_SHORT);
   double price = isShort ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl = res.entry.stopLoss;
   double tp = res.takeProfit;

   bool ok = isShort ? trade.Sell(lots, _Symbol, price, sl, tp, "DAX40-AsianSweep")
                      : trade.Buy(lots, _Symbol, price, sl, tp, "DAX40-AsianSweep");
   if(ok)
   {
      g_positionRefLevel = res.refLevel;
      g_tradesToday++;
   }
   else
   {
      PrintFormat("Fallo al abrir posición: %d - %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

bool FindOurPosition(ulong &ticketOut)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      ticketOut = ticket;
      return true;
   }
   return false;
}

void ManageOpenPosition(ulong ticket)
{
   if(!InpBreakevenEnabled) return;
   if(!PositionSelectByTicket(ticket)) return;

   double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   long type = PositionGetInteger(POSITION_TYPE);
   bool isShort = (type == POSITION_TYPE_SELL);

   if(MathAbs(sl - entryPrice) < _Point) return; // ya está en breakeven

   double currentPrice = isShort ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double riskPoints = MathAbs(entryPrice - sl) / _Point;
   if(riskPoints <= 0) return;
   double movePoints = isShort ? (entryPrice - currentPrice) / _Point : (currentPrice - entryPrice) / _Point;
   double rMultiple = movePoints / riskPoints;
   if(rMultiple <= InpBreakevenMinR) return;

   // BoS de 5m confirmado por cierre más allá del nivel de referencia
   // guardado al abrir la operación. NOTA: es una simplificación -- ver
   // dax_model/be_rule.py, misma limitación documentada ahí.
   MqlRates m5[];
   ArraySetAsSeries(m5, false);
   int n5 = CopyRates(_Symbol, PERIOD_M5, 1, 50, m5);
   if(n5 <= 0) return;
   int bosIdx = DetectMSS(m5, n5, g_positionRefLevel, isShort, 0, -1);
   if(bosIdx == -1) return;

   trade.PositionModify(ticket, entryPrice, tp);
}

//====================================================================
// CICLO PRINCIPAL
//====================================================================

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   InitDrawdownGuardrail();
   g_currentDayDate = 0;   // fuerza reset en el primer tick
   g_lastM5BarTime = 0;
   g_haltedByKillSwitch = false;
   return(INIT_SUCCEEDED);
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagicNumber) return;

   long entryType = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;

   double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                  + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                  + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
   if(profit < 0 && InpStopAfterFirstLoss) g_stoppedForDay = true;
}

void OnTick()
{
   MqlRates m5[];
   ArraySetAsSeries(m5, false);
   int n5 = CopyRates(_Symbol, PERIOD_M5, 1, LOOKBACK_M5, m5);
   if(n5 <= 0) return;

   datetime lastBarTime = m5[n5 - 1].time;
   if(lastBarTime == g_lastM5BarTime) return; // ya procesado este cierre de vela
   g_lastM5BarTime = lastBarTime;

   ResetDailyLimiterIfNewDay(TimeCurrent());

   DrawdownState dd = EvaluateDrawdown(AccountInfoDouble(ACCOUNT_EQUITY));
   if(dd == DD_HALTED)
   {
      if(!g_haltedByKillSwitch)
      {
         CloseAllPositions();
         Print("KILL-SWITCH: drawdown al 100% del límite. EA desactivado hasta reinicio manual.");
         g_haltedByKillSwitch = true;
      }
      return;
   }
   if(dd == DD_WARNING)
   {
      Print("AVISO: drawdown en zona de aviso (>=", InpDrawdownWarningPct, "% del límite). No se abrirán operaciones nuevas.");
      return;
   }

   ulong ourTicket;
   if(FindOurPosition(ourTicket))
   {
      ManageOpenPosition(ourTicket);
      return; // no evaluar setups nuevos mientras hay una posición abierta
   }

   if(!CanTrade()) return;

   double asianHigh, asianLow;
   int monitorStart;
   if(!ComputeAsianRange(m5, n5, asianHigh, asianLow, monitorStart)) return;

   MqlRates m15[];
   ArraySetAsSeries(m15, false);
   int n15 = CopyRates(_Symbol, PERIOD_M15, 1, LOOKBACK_M15, m15);

   MqlRates h1[];
   ArraySetAsSeries(h1, false);
   int n1h = CopyRates(_Symbol, PERIOD_H1, 1, LOOKBACK_H1, h1);

   int directions[2];
   directions[0] = BIAS_SHORT;
   directions[1] = BIAS_LONG;

   for(int d = 0; d < 2; d++)
   {
      SetupResult res;
      bool evaluated = EvaluateDirection(m5, n5, m15, n15, h1, n1h, asianHigh, asianLow, monitorStart, directions[d], res);
      if(!evaluated) continue;

      if(!res.taken)
      {
         PrintFormat("Setup descartado (%s): %s", directions[d] == BIAS_SHORT ? "SHORT" : "LONG", res.discardReason);
         continue;
      }

      OpenTradeFromSetup(res);
      break; // como mucho una apertura por evaluación; el límite diario lo controla CanTrade()
   }
}
