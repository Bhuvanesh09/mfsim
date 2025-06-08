# MFSIM: Mutual Fund Simulation & Backtesting System

## Project Overview

MFSIM is a comprehensive mutual fund backtesting and simulation system designed specifically for Indian mutual funds. It provides sophisticated portfolio management, strategy testing, and performance analysis capabilities with real-time data integration.

## Core Architecture

### 1. Backtester Engine (`backtester/`)

**Primary Component**: `simulator.py` - The heart of the backtesting system

**Key Features**:
- Historical backtesting with customizable date ranges
- SIP (Systematic Investment Plan) support with configurable frequencies (daily/weekly/monthly)
- Real-time portfolio rebalancing based on strategy logic
- Live NAV data integration via `api.mfapi.in` API
- Comprehensive transaction logging and audit trail
- Multi-fund portfolio tracking with unit-based accounting

**Core Methods**:
- `run()`: Main simulation execution
- `make_purchase()`: Execute fund purchases with unit calculations
- `_apply_sip()`: Handle systematic investment plans
- `_calculate_metrics()`: Compute performance metrics post-simulation

### 2. Strategy Framework (`strategies/`)

**Base Architecture**: Abstract strategy pattern with `BaseStrategy` class

**Available Strategies**:
- **MomentumValueStrategy**: Implements momentum-based allocation between two funds
  - Uses 180-day performance lookback for decision making
  - Performs semi-annual rebalancing with 10% allocation shifts
  - Compares momentum vs value fund performance dynamically

**Strategy Interface**:
- `allocate_money()`: Initial fund allocation logic
- `rebalance()`: Portfolio rebalancing decisions
- Configurable frequency and metrics tracking

### 3. Metrics System (`metrics/`)

**Performance Metrics Available**:

- **Total Return**: Simple portfolio return calculation
  ```python
  total_return = (final_value / money_invested) - 1
  ```

- **Sharpe Ratio**: Risk-adjusted returns with configurable risk-free rate
  - Supports daily/monthly frequency scaling
  - Default risk-free rate: 6% annually

- **Maximum Drawdown**: Peak-to-trough portfolio decline measurement
  ```python
  drawdown = (cumulative - rolling_max) / rolling_max
  ```

- **Sortino Ratio**: Downside deviation-focused risk metric
  - Considers only negative returns for risk calculation
  - More appropriate for asymmetric return distributions

**Metric Interface**: All metrics inherit from `BaseMetric` with standardized `calculate()` method

### 4. Data Management (`utils/`)

**Data Loader** (`data_loader.py`):
- **Base Interface**: All data loaders must subclass `BaseDataLoader` and implement `load_nav_data(fund_name)`, which returns a DataFrame with columns:
  - `date` (pandas datetime64): NAV date (sorted ascending)
  - `nav` (float): Net Asset Value for that date
- **Default Loader**: `MfApiDataLoader` fetches fund list and NAV data from `mf_list.json` and `api.mfapi.in`.
- **Custom Loaders**: Users can implement their own loader by subclassing `BaseDataLoader` and passing it to the `Simulator` via the `data_loader` argument.
- **Fund List Loading**: `load_fund_list()` is an implementation detail of `MfApiDataLoader` and not required in custom loaders.
- **Error Handling**: Robust exception handling for missing data

**Logging System** (`logger.py`):
- Dual output: File and console logging
- Timestamped log files in `logs/` directory
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Transaction-level audit trails

### 5. Data Storage (`data/`)

**mf_list.json**: Comprehensive database of Indian mutual funds
- Contains scheme codes, names, and metadata
- Used for fund selection and API integration
- Large dataset requiring careful memory management

## System Capabilities

### Investment Simulation Features

**Investment Types**:
- **Lump Sum**: One-time initial investment with equal fund allocation
- **SIP Support**: Regular investments with configurable frequencies
- **Mixed Approach**: Combination of lump sum + ongoing SIP

**Portfolio Management**:
- Multi-fund simultaneous tracking
- Unit-based accounting system
- Real-time portfolio valuation
- Complete transaction history maintenance

### Strategy Implementation

**Rebalancing Framework**:
- Configurable frequencies: daily, weekly, monthly, quarterly, semi-annually, annually
- Custom allocation logic via strategy classes
- Performance-based rebalancing decisions
- Transaction cost considerations (placeholder for future implementation)

**Decision Logic Examples**:
```python
# Momentum vs Value strategy logic
if momentum_returns > value_returns:
    # Shift 10% allocation from value to momentum
    shift_amount = 0.1 * value_holdings * current_nav
```

### Performance Analysis

**Risk Assessment**:
- Multiple risk metrics with industry-standard calculations
- Configurable risk-free rates and frequency scaling
- Portfolio value history reconstruction
- Drawdown analysis and peak detection

**Return Analysis**:
- Total return calculations with proper unit accounting
- Time-weighted return methodologies
- Portfolio-level performance aggregation

## Technical Implementation

### Data Flow Architecture

1. **Initialization Phase**:
   ```python
   from mfsim.utils.data_loader import MfApiDataLoader
   # Load fund universe (for MfApiDataLoader)
   data_loader = MfApiDataLoader()
   fund_list = data_loader.funds_list_df.schemeName.tolist()
   # Fetch NAV data via API
   nav_data = {fund: data_loader.load_nav_data(fund) for fund in fund_list}
   # Or, pass a custom loader to Simulator
   sim = Simulator(..., data_loader=CustomDataLoader(...))
   ```

2. **Simulation Loop**:
   ```python
   for date in date_range:
       # Apply SIP if scheduled
       if self._is_sip_date(date):
           self._apply_sip(date)
       
       # Rebalance if required
       if self._is_rebalance_date(date):
           orders = strategy.rebalance(portfolio, nav_data, date)
           self._execute_orders(orders)
   ```

3. **Performance Calculation**:
   ```python
   # Calculate metrics post-simulation
   for metric in strategy.metrics:
       result = metric.calculate(portfolio_history, current_portfolio, end_date, nav_data)
   ```

### External Dependencies

**API Integration**:
- **Data Source**: `api.mfapi.in` for live Indian mutual fund NAV data
- **Format**: JSON responses with historical NAV series
- **Rate Limiting**: Consider API limits for production usage

**Core Libraries**:
- **pandas**: DataFrame operations and time series handling
- **numpy**: Numerical computations and statistical calculations
- **requests**: HTTP client for API integration
- **datetime**: Date manipulation and range generation

## Usage Patterns

### Basic Simulation Example

```python
from mfsim.backtester import Simulator
from mfsim.strategies import MomentumValueStrategy

# Define strategy
strategy = MomentumValueStrategy(
    frequency='monthly',
    metrics=['Total Return', 'Sharpe Ratio', 'Maximum Drawdown'],
    value_fund="NIPPON INDIA NIFTY 50 VALUE 20 INDEX FUND - DIRECT Plan - IDCW Option",
    momentum_fund="BANDHAN NIFTY200 MOMENTUM 30 INDEX FUND - GROWTH - DIRECT PLAN",
    momentum_period=180
)

# Create simulator
sim = Simulator(
    start_date='2023-01-01',
    end_date='2024-01-01',
    initial_investment=10000,
    strategy=strategy,
    sip_amount=1000,
    sip_frequency='monthly'
)

# Execute simulation
results = sim.run()
print(f"Total Return: {results['TotalReturn']:.2%}")
print(f"Sharpe Ratio: {results['SharpeRatio']:.3f}")
```

### Custom Strategy Development

```python
from mfsim.strategies.base_strategy import BaseStrategy

class CustomStrategy(BaseStrategy):
    def __init__(self, frequency, metrics, fund_list, **kwargs):
        super().__init__(frequency, metrics, fund_list)
        # Custom initialization
    
    def rebalance(self, portfolio, nav_data, current_date):
        # Implement custom rebalancing logic
        orders = []
        # ... custom logic ...
        return orders
```

## System Strengths

**Architecture Benefits**:
- **Modular Design**: Clear separation of concerns across components
- **Extensible Framework**: Easy addition of new strategies and metrics
- **Real-time Integration**: Live data connectivity for current market conditions
- **Comprehensive Logging**: Complete audit trail for regulatory compliance
- **Flexible Configuration**: Customizable parameters for diverse investment scenarios

**Performance Features**:
- **Efficient Data Handling**: Optimized pandas operations for large datasets
- **Memory Management**: Lazy loading and data streaming capabilities
- **Scalable Architecture**: Support for multiple concurrent simulations

## Current Limitations & Future Enhancements

**Known Limitations**:
- **Transaction Costs**: Not currently factored into return calculations
- **Market Impact**: No slippage modeling for large trades
- **Tax Implications**: Tax-adjusted returns not implemented
- **Currency Effects**: Single currency (INR) assumption

**Planned Enhancements**:
- **Cost Modeling**: Integration of expense ratios and transaction fees
- **Advanced Metrics**: Addition of Alpha, Beta, Information Ratio
- **Visualization**: Portfolio performance charting and reporting
- **Multi-asset Support**: Extension beyond mutual funds to ETFs, stocks

## Development Status

**Current State**: Production-ready backtesting system with active development
**Last Updated**: Based on log files, actively used through September-October 2024
**API Status**: Successfully integrating with live Indian mutual fund data
**Testing Evidence**: Multiple simulation runs with real fund data validation

## File Structure Summary

```
mfsim/
├── backtester/          # Core simulation engine
├── strategies/          # Investment strategy implementations  
├── metrics/            # Performance calculation modules
├── utils/              # Data loading and utility functions
├── data/               # Static data files (fund lists)
├── logs/               # Simulation execution logs
└── tests/              # Test suite (placeholder)
```

This system represents a sophisticated, production-ready mutual fund backtesting framework with significant potential for investment strategy research, portfolio optimization, and quantitative finance applications in the Indian market context.
