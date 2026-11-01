"""Author and build the six courses the study harness was asked to ship.

Run:  python scripts/build_requested_courses.py

The six requested courses are AP Macroeconomics, AP Microeconomics, AP Biology,
AP Chemistry, Algebra 2 and AP Calculus. This script is the provenance record for
them: it holds their scope and sequence as data, writes it to
``app/ingest/seed/<id>.json``, builds the graph pack through the *ordinary*
``app.ingest.pipeline`` path, and then namespaces every concept id with the
course id.

Why the ids are namespaced
--------------------------
Concept ids are global - they key learner state, attempts and memory notes - and
``app.courses._node_index`` is a single flat map, so two courses that share a
concept title would silently resolve to whichever course was declared first. The
requested AP Biology course and the shipped Biology course genuinely share ideas
such as "Active transport", and Algebra 2 shares ideas with the authored algebra
course. Namespacing (``ap_biology_active_transport``) makes the two namespaces
disjoint by construction, which is the same guarantee ``app.course_builder``
already relies on for learner-created courses.

Licence position
----------------
Every outline here is an *original* scope and sequence authored for this project
and dedicated to the public domain under CC0, exactly like the bundled outlines
it sits beside. No third-party curriculum text is reproduced. The course
*frameworks* follow the publicly published unit organisation of the AP courses
and the topic organisation of Khan Academy, which is why each course also carries
Khan Academy and OpenStax links as study references. Those links are link-only:
nothing is fetched, copied or trained on, and ``app.ingest.policy`` refuses them
at the gate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEED_DIR = BACKEND / 'app' / 'ingest' / 'seed'
PACK_DIR = BACKEND / 'app' / 'curriculum_packs'

#: Concept ids must fit the receipt schema, which caps them at 64 characters.
MAX_ID = 64

ATTRIBUTION = ('Original scope and sequence authored for the Luminfest Learning Harness, '
               'dedicated to the public domain under CC0.')
SCOPE = ('Structure only: concept titles, unit order and prerequisite intent. No third-party '
         'curriculum text is reproduced, and no restricted source is ingested.')


def c(title, summary, keywords=(), prerequisites=()):
    """One concept: a title, a one-line summary, keywords and declared prerequisites.

    Prerequisites name other concepts *by title*, which is the reference form the
    ingest classifier resolves against its own title index.
    """
    entry = {'title': title, 'summary': summary}
    if keywords:
        entry['keywords'] = list(keywords)
    if prerequisites:
        entry['prerequisites'] = list(prerequisites)
    return entry


# ============================================================ AP Macroeconomics
AP_MACROECONOMICS = {
    'id': 'ap_macroeconomics',
    'title': 'AP Macroeconomics',
    'subject': 'Economics',
    'subject_kind': 'social_science',
    'expected_weeks': 30,
    'description': ('The whole-economy view: scarcity and market fundamentals, national income '
                    'and price determination, the financial sector, stabilisation policy and '
                    'its long-run consequences, and the open economy.'),
    'course': 'AP Macroeconomics - Scarcity, Stabilisation and the Open Economy',
    'strands': [
        {'strand': 'Basic Economic Concepts', 'units': [
            {'unit': 'Scarcity and choice', 'topics': [
                {'topic': 'Foundations of economic reasoning', 'concepts': [
                    c('Scarcity and opportunity cost',
                      'Every choice costs the next-best alternative forgone, so scarcity is about '
                      'trade-offs rather than a temporary shortage.',
                      ['scarcity', 'opportunity cost', 'trade-off']),
                    c('Production possibilities curve',
                      'The frontier shows the maximum output combinations and the opportunity cost '
                      'of moving along it.',
                      ['production possibilities', 'frontier', 'efficiency'],
                      ['Scarcity and opportunity cost']),
                    c('Comparative advantage and gains from trade',
                      'Specialising where the opportunity cost is lowest raises total output, which '
                      'is why voluntary trade can benefit both sides.',
                      ['comparative advantage', 'specialisation', 'trade'],
                      ['Production possibilities curve']),
                    c('Marginal analysis and decision rules',
                      'A rational decision compares the marginal benefit of one more unit with its '
                      'marginal cost, not the totals.',
                      ['marginal benefit', 'marginal cost'],
                      ['Scarcity and opportunity cost']),
                ]},
            ]},
            {'unit': 'Demand, supply and equilibrium', 'topics': [
                {'topic': 'The market model', 'concepts': [
                    c('Demand and the law of demand',
                      'Quantity demanded falls as price rises, holding every other influence '
                      'constant.',
                      ['demand', 'law of demand'],
                      ['Marginal analysis and decision rules']),
                    c('Supply and the law of supply',
                      'Quantity supplied rises as price rises because a higher price makes '
                      'production more profitable at the margin.',
                      ['supply', 'law of supply'],
                      ['Marginal analysis and decision rules']),
                    c('Market equilibrium and disequilibrium',
                      'Price settles where quantity demanded equals quantity supplied; a mismatch '
                      'shows up as a surplus or a shortage.',
                      ['equilibrium', 'surplus', 'shortage'],
                      ['Demand and the law of demand', 'Supply and the law of supply']),
                    c('Determinants of demand and supply',
                      'Non-price influences shift the curves, and a shift moves equilibrium price '
                      'and quantity together.',
                      ['curve shift', 'determinants'],
                      ['Market equilibrium and disequilibrium']),
                    c('Consumer and producer surplus',
                      'Surplus measures the gain from trade: what buyers would have paid above '
                      'price, and what sellers would have accepted below it.',
                      ['consumer surplus', 'producer surplus'],
                      ['Market equilibrium and disequilibrium']),
                    c('Market efficiency and deadweight loss',
                      'Total surplus is maximised at equilibrium, so any move away from it destroys '
                      'some surplus as deadweight loss.',
                      ['efficiency', 'deadweight loss'],
                      ['Consumer and producer surplus']),
                    c('Price ceilings and price floors',
                      'A binding ceiling creates a shortage and a binding floor creates a surplus, '
                      'because neither changes the underlying curves.',
                      ['price ceiling', 'price floor'],
                      ['Market efficiency and deadweight loss']),
                ]},
            ]},
        ]},
        {'strand': 'Economic Indicators and the Business Cycle', 'units': [
            {'unit': 'Measuring output', 'prerequisites': ['Demand, supply and equilibrium'],
             'topics': [
                {'topic': 'Output and growth', 'concepts': [
                    c('Gross domestic product',
                      'GDP is the market value of final goods and services produced inside a '
                      'country during a period.',
                      ['GDP', 'output', 'final goods'],
                      ['Market equilibrium and disequilibrium']),
                    c('Real versus nominal GDP',
                      'Deflating nominal GDP by a price index separates a change in output from a '
                      'change in prices.',
                      ['real GDP', 'nominal GDP', 'deflator'],
                      ['Gross domestic product']),
                    c('Limitations of GDP as a measure',
                      'GDP omits unpaid work, inequality, environmental cost and leisure, so it '
                      'measures production rather than welfare.',
                      ['welfare', 'limitations of GDP'],
                      ['Real versus nominal GDP']),
                    c('Economic growth and productivity',
                      'Long-run living standards rise with productivity, which depends on physical '
                      'capital, human capital and technology.',
                      ['growth', 'productivity', 'human capital'],
                      ['Real versus nominal GDP']),
                ]},
            ]},
            {'unit': 'Inflation, unemployment and the cycle', 'prerequisites': ['Measuring output'],
             'topics': [
                {'topic': 'Prices and jobs', 'concepts': [
                    c('Unemployment: measurement and types',
                      'Frictional, structural and cyclical unemployment are distinguished by their '
                      'cause, and only some respond to demand policy.',
                      ['unemployment', 'frictional', 'structural', 'cyclical']),
                    c('Labour force participation',
                      'Participation measures the share of the working-age population working or '
                      'seeking work, and it moves with the cycle.',
                      ['labour force', 'participation'],
                      ['Unemployment: measurement and types']),
                    c('Inflation and the consumer price index',
                      'A price index tracks the cost of a fixed basket, and its percentage change '
                      'is the inflation rate.',
                      ['inflation', 'CPI', 'price index']),
                    c('Costs of inflation',
                      'Expected inflation is manageable, but unanticipated inflation redistributes '
                      'wealth between borrowers and lenders.',
                      ['inflation', 'redistribution', 'purchasing power'],
                      ['Inflation and the consumer price index']),
                    c('Business cycle phases',
                      'Expansion, peak, contraction and trough describe the recurring but irregular '
                      'pattern of output and employment.',
                      ['business cycle', 'recession', 'expansion'],
                      ['Unemployment: measurement and types']),
                ]},
            ]},
        ]},
        {'strand': 'National Income and Price Determination', 'units': [
            {'unit': 'The aggregate demand-aggregate supply model',
             'prerequisites': ['Inflation, unemployment and the cycle'], 'topics': [
                {'topic': 'AD, SRAS and LRAS', 'concepts': [
                    c('Aggregate demand',
                      'AD slopes downward because a lower price level raises real wealth, lowers '
                      'interest rates and raises net exports.',
                      ['aggregate demand', 'real wealth effect'],
                      ['Business cycle phases']),
                    c('Shifts in aggregate demand',
                      'Spending shocks shift AD, and how much output changes depends on the slope '
                      'of short-run aggregate supply.',
                      ['aggregate demand shift', 'spending shock'],
                      ['Aggregate demand']),
                    c('Short-run aggregate supply',
                      'SRAS slopes upward because some input prices and wages are sticky in the '
                      'short run.',
                      ['short-run aggregate supply', 'sticky prices']),
                    c('Long-run aggregate supply',
                      'LRAS is vertical at potential output, set by productive capacity rather '
                      'than the price level.',
                      ['long-run aggregate supply', 'potential output'],
                      ['Short-run aggregate supply']),
                    c('Macroeconomic equilibrium and output gaps',
                      'Where AD meets SRAS gives short-run output, and the distance from LRAS '
                      'signals inflationary or recessionary pressure.',
                      ['equilibrium', 'output gap'],
                      ['Aggregate demand', 'Short-run aggregate supply',
                       'Long-run aggregate supply']),
                ]},
            ]},
            {'unit': 'Fiscal policy', 'prerequisites': ['The aggregate demand-aggregate supply model'],
             'topics': [
                {'topic': 'Taxing and spending', 'concepts': [
                    c('Fiscal policy: spending and taxation',
                      'Government shifts aggregate demand directly through spending and indirectly '
                      'through taxes and transfers.',
                      ['fiscal policy', 'government spending', 'taxation'],
                      ['Macroeconomic equilibrium and output gaps']),
                    c('The spending multiplier',
                      'An initial spending change produces a larger total change because each '
                      'round of income is partly re-spent.',
                      ['spending multiplier', 'marginal propensity to consume'],
                      ['Fiscal policy: spending and taxation']),
                    c('Automatic stabilizers',
                      'Taxes and transfers that vary with income dampen the cycle without any new '
                      'legislation.',
                      ['automatic stabilizers', 'built-in stability'],
                      ['Fiscal policy: spending and taxation']),
                    c('Crowding out',
                      'Deficit spending can raise interest rates and displace private investment, '
                      'reducing the net stimulus.',
                      ['crowding out', 'interest rate'],
                      ['Fiscal policy: spending and taxation']),
                    c('Supply-side fiscal policy',
                      'Policies aimed at incentives can raise potential output rather than merely '
                      'shifting demand.',
                      ['supply-side', 'incentives'],
                      ['Fiscal policy: spending and taxation']),
                ]},
            ]},
        ]},
        {'strand': 'The Financial Sector', 'units': [
            {'unit': 'Money, banking and interest',
             'prerequisites': ['Fiscal policy'], 'topics': [
                {'topic': 'Money and the money market', 'concepts': [
                    c('Functions and measures of money',
                      'Money is a medium of exchange, a unit of account and a store of value, and '
                      'M1 and M2 measure it by liquidity.',
                      ['money', 'M1', 'M2', 'liquidity']),
                    c('Banking and money creation',
                      'Banks create deposits by lending out reserves, so the money supply exceeds '
                      'the monetary base.',
                      ['bank', 'reserves', 'deposits'],
                      ['Functions and measures of money']),
                    c('The money multiplier',
                      'Maximum deposit expansion is the reciprocal of the reserve ratio, and it '
                      'shrinks with leakage into cash.',
                      ['money multiplier', 'reserve ratio'],
                      ['Banking and money creation']),
                    c('Money demand and the money market',
                      'Money demand depends on income and interest rates, and equilibrium sets the '
                      'short-term interest rate.',
                      ['money demand', 'interest rate'],
                      ['Functions and measures of money']),
                    c('The loanable funds market',
                      'The real interest rate balances saving with investment demand, linking the '
                      'financial and goods markets.',
                      ['loanable funds', 'real interest rate'],
                      ['Money demand and the money market']),
                ]},
            ]},
            {'unit': 'Central banking and monetary policy', 'prerequisites': ['Money, banking and interest'],
             'topics': [
                {'topic': 'Policy tools and transmission', 'concepts': [
                    c('Central banks and monetary policy tools',
                      'Open-market operations, reserve requirements and the administered rate '
                      'change reserves and short-term interest rates.',
                      ['central bank', 'open market operations', 'monetary policy'],
                      ['Money demand and the money market']),
                    c('Transmission of monetary policy',
                      'A rate change works through investment, consumption and net exports, and it '
                      'arrives with a lag.',
                      ['transmission mechanism', 'investment'],
                      ['Central banks and monetary policy tools']),
                    c('Interest rates and investment',
                      'Lower real interest rates raise the present value of future returns, so '
                      'investment spending rises.',
                      ['interest rate', 'investment'],
                      ['The loanable funds market']),
                    c('The short-run Phillips curve',
                      'The short-run trade-off between inflation and unemployment arises from '
                      'sticky prices and surprise inflation.',
                      ['Phillips curve', 'inflation', 'unemployment'],
                      ['Transmission of monetary policy']),
                ]},
            ]},
        ]},
        {'strand': 'Long-Run Consequences of Stabilization Policies', 'units': [
            {'unit': 'Expectations and the long run',
             'prerequisites': ['Central banking and monetary policy'], 'topics': [
                {'topic': 'Long-run neutrality and the debt', 'concepts': [
                    c('The long-run Phillips curve',
                      'In the long run the trade-off disappears: unemployment returns to its '
                      'natural rate whatever the inflation rate.',
                      ['long-run Phillips curve', 'natural rate'],
                      ['The short-run Phillips curve']),
                    c('Expectations and credibility',
                      'Once expectations adjust, only surprise inflation moves output, so '
                      'central-bank credibility has real value.',
                      ['expectations', 'credibility'],
                      ['The long-run Phillips curve']),
                    c('Monetary policy in the long run',
                      'Money is neutral in the long run: it affects the price level rather than '
                      'real output.',
                      ['neutrality of money', 'price level'],
                      ['The long-run Phillips curve']),
                    c('Fiscal policy in the long run',
                      'Persistent deficits can crowd out capital formation and shift the burden '
                      'toward future taxpayers.',
                      ['deficit', 'debt', 'long run'],
                      ['Crowding out']),
                    c('Deficits, debt and sustainability',
                      'Sustainability depends on the gap between the interest rate and the growth '
                      'rate, not on the debt level alone.',
                      ['debt sustainability', 'interest growth gap'],
                      ['Fiscal policy in the long run']),
                    c('Policies to promote growth',
                      'Policies that raise saving, investment, human capital and technology raise '
                      'long-run potential output.',
                      ['growth policy', 'human capital'],
                      ['Economic growth and productivity']),
                ]},
            ]},
        ]},
        {'strand': 'Open Economy: International Trade and Finance', 'units': [
            {'unit': 'Trade and the balance of payments',
             'prerequisites': ['Expectations and the long run'], 'topics': [
                {'topic': 'Accounts and barriers', 'concepts': [
                    c('Balance of payments accounts',
                      'The current account and the financial account offset each other, so a trade '
                      'deficit is matched by net capital inflow.',
                      ['balance of payments', 'current account', 'financial account']),
                    c('Trade barriers and their effects',
                      'Tariffs and quotas raise domestic prices, reduce imports and destroy some '
                      'surplus as deadweight loss.',
                      ['tariff', 'quota', 'trade barrier'],
                      ['Balance of payments accounts']),
                ]},
            ]},
            {'unit': 'Exchange rates and policy', 'prerequisites': ['Trade and the balance of payments'],
             'topics': [
                {'topic': 'Currencies and regimes', 'concepts': [
                    c('Exchange rates and the foreign exchange market',
                      'The exchange rate is the price of one currency in another, set by the supply '
                      'of and demand for currencies.',
                      ['exchange rate', 'foreign exchange market'],
                      ['Balance of payments accounts']),
                    c('Determinants of exchange rates',
                      'Interest-rate differentials, relative inflation and trade flows move currency '
                      'demand and supply.',
                      ['interest rate differential', 'exchange rate'],
                      ['Exchange rates and the foreign exchange market']),
                    c('Appreciation, depreciation and net exports',
                      'A weaker currency makes exports cheaper abroad, which raises net exports and '
                      'shifts aggregate demand.',
                      ['appreciation', 'depreciation', 'net exports'],
                      ['Determinants of exchange rates']),
                    c('Open-economy policy linkages',
                      'With mobile capital, monetary and fiscal policy work differently under fixed '
                      'and floating exchange-rate regimes.',
                      ['fixed exchange rate', 'floating exchange rate'],
                      ['Appreciation, depreciation and net exports']),
                ]},
            ]},
        ]},
    ],
}


# ============================================================ AP Microeconomics
AP_MICROECONOMICS = {
    'id': 'ap_microeconomics',
    'title': 'AP Microeconomics',
    'subject': 'Economics',
    'subject_kind': 'social_science',
    'expected_weeks': 30,
    'description': ('The firm-and-market view: scarcity and marginal analysis, supply and demand '
                    'with elasticity, production and cost, market structure from perfect '
                    'competition to oligopoly, factor markets, and market failure.'),
    'course': 'AP Microeconomics - Markets, Firms and Market Failure',
    'strands': [
        {'strand': 'Basic Economic Concepts', 'units': [
            {'unit': 'Scarcity, choice and marginal analysis', 'topics': [
                {'topic': 'Foundations', 'concepts': [
                    c('Scarcity, choice and opportunity cost',
                      'Every choice costs the next-best alternative forgone, which is the source '
                      'of all trade-offs.',
                      ['scarcity', 'opportunity cost']),
                    c('Production possibilities curve',
                      'The frontier shows the maximum output combinations and the opportunity cost '
                      'of moving along it.',
                      ['production possibilities', 'frontier'],
                      ['Scarcity, choice and opportunity cost']),
                    c('Comparative advantage and gains from trade',
                      'Specialising where opportunity cost is lowest raises total output, so trade '
                      'can benefit both sides.',
                      ['comparative advantage', 'trade'],
                      ['Production possibilities curve']),
                    c('Marginal analysis and decision rules',
                      'A rational decision compares the marginal benefit of one more unit with its '
                      'marginal cost.',
                      ['marginal benefit', 'marginal cost'],
                      ['Scarcity, choice and opportunity cost']),
                    c('Utility and marginal utility',
                      'Total utility rises with consumption while marginal utility generally falls.',
                      ['utility', 'marginal utility'],
                      ['Marginal analysis and decision rules']),
                    c('Marginal utility per dollar and consumer choice',
                      'A consumer maximises utility by equalising marginal utility per dollar '
                      'across all goods.',
                      ['marginal utility per dollar', 'consumer equilibrium'],
                      ['Utility and marginal utility']),
                    c('Budget constraints and trade-offs',
                      'A budget line shows the affordable combinations, and its slope is the '
                      'relative price.',
                      ['budget constraint', 'relative price'],
                      ['Marginal utility per dollar and consumer choice']),
                ]},
            ]},
        ]},
        {'strand': 'Supply and Demand', 'units': [
            {'unit': 'Elasticity', 'prerequisites': ['Scarcity, choice and marginal analysis'],
             'topics': [
                {'topic': 'Responsiveness of quantity', 'concepts': [
                    c('Price elasticity of demand',
                      'Elasticity measures the percentage change in quantity demanded for a one '
                      'per cent change in price.',
                      ['elasticity of demand', 'responsiveness'],
                      ['Budget constraints and trade-offs']),
                    c('Determinants of price elasticity of demand',
                      'Substitutes, share of budget, necessity and time horizon decide how '
                      'responsive demand is.',
                      ['substitutes', 'elasticity determinants'],
                      ['Price elasticity of demand']),
                    c('Price elasticity of supply',
                      'Supply elasticity depends on how quickly producers can change output, so it '
                      'is larger in the long run.',
                      ['elasticity of supply'],
                      ['Price elasticity of demand']),
                    c('Income and cross-price elasticity',
                      'Income elasticity classifies normal and inferior goods, and cross-price '
                      'elasticity identifies substitutes and complements.',
                      ['income elasticity', 'cross-price elasticity'],
                      ['Price elasticity of demand']),
                    c('Elasticity and total revenue',
                      'Total revenue rises with price only when demand is inelastic, which is the '
                      'practical use of the measure.',
                      ['total revenue', 'elasticity'],
                      ['Price elasticity of demand']),
                ]},
            ]},
            {'unit': 'Welfare, taxes and intervention', 'prerequisites': ['Elasticity'],
             'topics': [
                {'topic': 'Surplus and policy', 'concepts': [
                    c('Consumer and producer surplus',
                      'Surplus measures the gain from trade for buyers and sellers separately.',
                      ['consumer surplus', 'producer surplus'],
                      ['Elasticity and total revenue']),
                    c('Market efficiency and total surplus',
                      'Total surplus is maximised at competitive equilibrium, which is the '
                      'efficiency benchmark for every later comparison.',
                      ['efficiency', 'total surplus'],
                      ['Consumer and producer surplus']),
                    c('Taxes and tax incidence',
                      'The statutory payer is not the economic bearer: incidence follows the '
                      'relative elasticities.',
                      ['tax incidence', 'tax burden'],
                      ['Market efficiency and total surplus']),
                    c('Deadweight loss of taxation',
                      'A tax drives a wedge between price paid and price received, so some '
                      'mutually beneficial trades do not happen.',
                      ['deadweight loss', 'tax wedge'],
                      ['Taxes and tax incidence']),
                    c('Subsidies',
                      'A subsidy lowers the price buyers pay and raises the price sellers receive, '
                      'at a cost to the government.',
                      ['subsidy', 'government cost'],
                      ['Deadweight loss of taxation']),
                    c('Price ceilings and floors',
                      'A binding ceiling creates a shortage and a binding floor a surplus, with '
                      'deadweight loss in both cases.',
                      ['price ceiling', 'price floor'],
                      ['Market efficiency and total surplus']),
                    c('International trade and tariffs',
                      'Opening trade raises total surplus while a tariff lowers it, though it '
                      'redistributes toward domestic producers.',
                      ['tariff', 'trade', 'comparative advantage'],
                      ['Deadweight loss of taxation']),
                ]},
            ]},
        ]},
        {'strand': 'Production, Cost, and the Perfect Competition Model', 'units': [
            {'unit': 'Production and cost', 'prerequisites': ['Welfare, taxes and intervention'],
             'topics': [
                {'topic': 'Cost structure', 'concepts': [
                    c('Explicit and implicit costs',
                      'Economic cost includes the opportunity cost of resources the owner already '
                      'supplies.',
                      ['explicit cost', 'implicit cost'],
                      ['Market efficiency and total surplus']),
                    c('Accounting profit versus economic profit',
                      'Economic profit subtracts implicit cost as well, so a firm can be '
                      'accounting-profitable and economically breaking even.',
                      ['accounting profit', 'economic profit', 'normal profit'],
                      ['Explicit and implicit costs']),
                    c('Short-run production and diminishing returns',
                      'With one input fixed, the marginal product of the variable input eventually '
                      'falls.',
                      ['diminishing returns', 'marginal product'],
                      ['Explicit and implicit costs']),
                    c('Short-run cost curves',
                      'Marginal cost crosses average variable and average total cost at their '
                      'minimum points.',
                      ['marginal cost', 'average total cost', 'average variable cost'],
                      ['Short-run production and diminishing returns']),
                    c('Long-run average total cost and economies of scale',
                      'All inputs vary in the long run, so the planning curve shows economies, '
                      'constant returns and diseconomies of scale.',
                      ['long-run average cost', 'economies of scale'],
                      ['Short-run cost curves']),
                ]},
            ]},
            {'unit': 'Perfect competition', 'prerequisites': ['Production and cost'], 'topics': [
                {'topic': 'A price-taking market', 'concepts': [
                    c('Perfect competition: characteristics',
                      'Many small firms, a homogeneous product and free entry make each firm a '
                      'price taker.',
                      ['perfect competition', 'price taker'],
                      ['Long-run average total cost and economies of scale']),
                    c('Profit maximisation where marginal revenue equals marginal cost',
                      'Every firm maximises profit by producing where marginal revenue equals '
                      'marginal cost.',
                      ['profit maximisation', 'marginal revenue'],
                      ['Perfect competition: characteristics', 'Short-run cost curves']),
                    c('Short-run equilibrium in perfect competition',
                      'Price equals marginal revenue for a price taker, so the firm produces where '
                      'price equals marginal cost.',
                      ['short-run equilibrium', 'price equals marginal cost'],
                      ['Profit maximisation where marginal revenue equals marginal cost']),
                    c('Long-run equilibrium and normal profit',
                      'Free entry drives economic profit to zero, leaving firms earning only a '
                      'normal profit.',
                      ['long-run equilibrium', 'zero economic profit', 'entry'],
                      ['Short-run equilibrium in perfect competition']),
                    c('Shutdown and exit decisions',
                      'A firm shuts down in the short run when price falls below average variable '
                      'cost, and exits when it falls below average total cost.',
                      ['shutdown point', 'exit', 'sunk cost'],
                      ['Short-run cost curves']),
                    c('Productive and allocative efficiency',
                      'Perfect competition is both productively and allocatively efficient in '
                      'long-run equilibrium.',
                      ['productive efficiency', 'allocative efficiency'],
                      ['Long-run equilibrium and normal profit']),
                ]},
            ]},
        ]},
        {'strand': 'Imperfect Competition', 'units': [
            {'unit': 'Monopoly', 'prerequisites': ['Perfect competition'], 'topics': [
                {'topic': 'Market power', 'concepts': [
                    c('Monopoly: sources of market power',
                      'Barriers to entry such as control of a resource, patents, or scale keep '
                      'rivals out and create a price maker.',
                      ['monopoly', 'barriers to entry', 'price maker'],
                      ['Productive and allocative efficiency']),
                    c('Monopoly profit maximisation',
                      'A monopolist sets output where marginal revenue equals marginal cost and '
                      'prices off the demand curve.',
                      ['monopoly output', 'marginal revenue'],
                      ['Monopoly: sources of market power']),
                    c('Monopoly inefficiency and deadweight loss',
                      'Restricting output below the competitive level leaves some mutually '
                      'beneficial trades unmade.',
                      ['deadweight loss', 'monopoly inefficiency'],
                      ['Monopoly profit maximisation']),
                    c('Price discrimination',
                      'Charging different prices to different buyers raises profit when groups can '
                      'be separated and resale is blocked.',
                      ['price discrimination', 'consumer surplus'],
                      ['Monopoly profit maximisation']),
                    c('Natural monopoly and regulation',
                      'When scale makes one firm cheapest, regulation targets the price rather '
                      'than the number of firms.',
                      ['natural monopoly', 'regulation'],
                      ['Monopoly inefficiency and deadweight loss']),
                ]},
            ]},
            {'unit': 'Strategic interaction', 'prerequisites': ['Monopoly'], 'topics': [
                {'topic': 'Between competition and monopoly', 'concepts': [
                    c('Monopolistic competition',
                      'Many firms sell differentiated products, so each faces a downward-sloping '
                      'demand curve but no barrier to entry.',
                      ['monopolistic competition', 'product differentiation'],
                      ['Monopoly: sources of market power']),
                    c('Monopolistic competition in the long run',
                      'Entry erodes profit until price equals average total cost, leaving excess '
                      'capacity.',
                      ['long-run equilibrium', 'excess capacity'],
                      ['Monopolistic competition']),
                    c('Oligopoly and interdependence',
                      'A few large firms must anticipate each other, so decisions are strategic '
                      'rather than independent.',
                      ['oligopoly', 'interdependence'],
                      ['Monopolistic competition in the long run']),
                    c('Game theory and Nash equilibrium',
                      'A Nash equilibrium is a set of strategies where no player can gain by '
                      'changing alone.',
                      ['game theory', 'Nash equilibrium'],
                      ['Oligopoly and interdependence']),
                    c('Collusion and cartels',
                      'Firms can raise joint profit by acting as a monopolist, but each has an '
                      'incentive to cheat.',
                      ['collusion', 'cartel', 'prisoner dilemma'],
                      ['Game theory and Nash equilibrium']),
                ]},
            ]},
        ]},
        {'strand': 'Factor Markets', 'units': [
            {'unit': 'Labour, capital and income', 'prerequisites': ['Strategic interaction'],
             'topics': [
                {'topic': 'Derived demand', 'concepts': [
                    c('Derived demand for labour',
                      'Demand for a factor exists only because the factor helps produce a good '
                      'that is itself demanded.',
                      ['derived demand', 'factor market'],
                      ['Collusion and cartels']),
                    c('Marginal revenue product',
                      'A firm hires until the marginal revenue product of the factor equals its '
                      'price.',
                      ['marginal revenue product', 'factor demand'],
                      ['Derived demand for labour']),
                    c('Competitive labour market equilibrium',
                      'In a competitive market the wage equals marginal revenue product for every '
                      'worker hired.',
                      ['wage determination', 'competitive labour market'],
                      ['Marginal revenue product']),
                    c('Monopsony',
                      'A single buyer of labour hires less and pays less than a competitive market '
                      'would.',
                      ['monopsony', 'exploitation'],
                      ['Competitive labour market equilibrium']),
                    c('Unions and bilateral bargaining',
                      'Collective bargaining raises wages through higher demand or restricted '
                      'supply, with employment effects.',
                      ['union', 'collective bargaining'],
                      ['Monopsony']),
                    c('Capital markets and the rental price of capital',
                      'Firms hire capital until its marginal revenue product equals the rental '
                      'price.',
                      ['rental price of capital', 'factor demand'],
                      ['Marginal revenue product']),
                    c('Present value and investment decisions',
                      'A project is worth funding when the present value of its returns exceeds '
                      'its cost.',
                      ['present value', 'discount rate'],
                      ['Capital markets and the rental price of capital']),
                    c('Least-cost combination of inputs',
                      'Cost is minimised where the marginal product per dollar is equal across '
                      'inputs.',
                      ['least-cost combination', 'marginal product per dollar'],
                      ['Present value and investment decisions']),
                ]},
            ]},
        ]},
        {'strand': 'Market Failure and the Role of Government', 'units': [
            {'unit': 'Externalities and public goods', 'prerequisites': ['Labour, capital and income'],
             'topics': [
                {'topic': 'When markets fail', 'concepts': [
                    c('Positive and negative externalities',
                      'An externality is a cost or benefit that falls on a third party outside the '
                      'transaction.',
                      ['externality', 'third party'],
                      ['Least-cost combination of inputs']),
                    c('Marginal social cost and marginal social benefit',
                      'Social cost and benefit add the external effect to the private one, which '
                      'is where the efficient quantity sits.',
                      ['marginal social cost', 'marginal social benefit'],
                      ['Positive and negative externalities']),
                    c('Coase theorem and property rights',
                      'With clear property rights and low bargaining cost, private parties can '
                      'reach the efficient outcome themselves.',
                      ['Coase theorem', 'property rights'],
                      ['Marginal social cost and marginal social benefit']),
                    c('Corrective taxes and subsidies',
                      'A tax equal to the external cost, or a subsidy equal to the external '
                      'benefit, realigns private with social incentives.',
                      ['corrective tax', 'Pigouvian subsidy'],
                      ['Marginal social cost and marginal social benefit']),
                    c('Public goods and the free-rider problem',
                      'Non-rival and non-excludable goods are underprovided because each user can '
                      'free ride.',
                      ['public good', 'free rider', 'non-rival'],
                      ['Corrective taxes and subsidies']),
                    c('Common resources and the tragedy of the commons',
                      'Rival but non-excludable resources are overused because no one bears the '
                      'full cost of their own use.',
                      ['common resource', 'tragedy of the commons'],
                      ['Public goods and the free-rider problem']),
                    c('Asymmetric information',
                      'When one side knows more, adverse selection and moral hazard can drive good '
                      'participants out of the market.',
                      ['asymmetric information', 'adverse selection', 'moral hazard'],
                      ['Corrective taxes and subsidies']),
                    c('Antitrust policy and regulation',
                      'Competition policy targets market power, while regulation can address '
                      'natural monopoly directly.',
                      ['antitrust', 'regulation'],
                      ['Monopoly inefficiency and deadweight loss']),
                    c('Income inequality and redistribution',
                      'Tax-and-transfer policy can change the distribution of income, with '
                      'efficiency costs of its own.',
                      ['income inequality', 'redistribution', 'Lorenz curve'],
                      ['Corrective taxes and subsidies']),
                ]},
            ]},
        ]},
    ],
}


# ================================================================ AP Biology
AP_BIOLOGY = {
    'id': 'ap_biology',
    'title': 'AP Biology',
    'subject': 'Biology',
    'subject_kind': 'science',
    'expected_weeks': 34,
    'description': ('The AP Biology course framework: the chemistry of life, cell structure and '
                    'function, cellular energetics, cell communication and the cell cycle, '
                    'heredity, gene expression and regulation, natural selection, and ecology.'),
    'course': 'AP Biology - Molecules, Cells, Heredity and Ecology',
    'strands': [
        {'strand': 'Chemistry of Life', 'units': [
            {'unit': 'Water and biological molecules', 'topics': [
                {'topic': 'The chemistry that life is built from', 'concepts': [
                    c('Structure of water and hydrogen bonding',
                      'Hydrogen bonding gives water cohesion, adhesion, a high specific heat and '
                      'solvent power, which is why life depends on it.',
                      ['water', 'hydrogen bond', 'cohesion', 'specific heat']),
                    c('Elements of life',
                      'Carbon, hydrogen, oxygen, nitrogen, phosphorus and sulfur build the '
                      'molecules of life.',
                      ['carbon', 'elements', 'CHONPS'],
                      ['Structure of water and hydrogen bonding']),
                    c('Biological macromolecules: carbohydrates',
                      'Simple sugars join into polysaccharides that serve as fuel or as structural '
                      'material.',
                      ['carbohydrate', 'monosaccharide', 'polysaccharide'],
                      ['Elements of life']),
                    c('Biological macromolecules: lipids',
                      'Fats store energy densely while phospholipids build the membranes that '
                      'compartmentalise cells.',
                      ['lipid', 'triglyceride', 'phospholipid'],
                      ['Elements of life']),
                    c('Biological macromolecules: proteins',
                      'A protein folds into a shape determined by its amino acid sequence, and the '
                      'shape determines its function.',
                      ['protein', 'amino acid', 'folding'],
                      ['Elements of life']),
                    c('Biological macromolecules: nucleic acids',
                      'DNA stores information in a stable double strand while RNA carries and '
                      'interprets it.',
                      ['DNA', 'RNA', 'nucleotide'],
                      ['Biological macromolecules: proteins']),
                ]},
            ]},
            {'unit': 'Enzymes and reaction conditions', 'prerequisites': ['Water and biological molecules'],
             'topics': [
                {'topic': 'Catalysis in cells', 'concepts': [
                    c('Enzymes as biological catalysts',
                      'Enzymes lower activation energy and are unchanged by the reaction they '
                      'speed up.',
                      ['enzyme', 'catalyst', 'activation energy'],
                      ['Biological macromolecules: proteins']),
                    c('Enzyme structure and the active site',
                      'A substrate binds a specific active site, and the induced fit grips it more '
                      'tightly.',
                      ['active site', 'induced fit', 'substrate'],
                      ['Enzymes as biological catalysts']),
                    c('Factors affecting enzyme activity',
                      'Temperature, pH and substrate concentration change rate, and beyond the '
                      'optimum the enzyme denatures.',
                      ['temperature', 'pH', 'denaturation'],
                      ['Enzyme structure and the active site']),
                    c('Enzyme inhibition and regulation',
                      'Competitive and non-competitive inhibitors slow a reaction, and allosteric '
                      'regulation tunes it.',
                      ['inhibition', 'allosteric', 'competitive'],
                      ['Factors affecting enzyme activity']),
                    c('pH, buffers and cellular conditions',
                      'Buffers resist pH change, which keeps enzyme shape and function stable.',
                      ['buffer', 'pH', 'homeostasis'],
                      ['Factors affecting enzyme activity']),
                ]},
            ]},
        ]},
        {'strand': 'Cell Structure and Function', 'units': [
            {'unit': 'Cell architecture', 'prerequisites': ['Enzymes and reaction conditions'],
             'topics': [
                {'topic': 'Building a cell', 'concepts': [
                    c('Cell structure: prokaryotic and eukaryotic',
                      'Prokaryotes lack membrane-bound organelles, which is the deepest structural '
                      'divide among cells.',
                      ['prokaryote', 'eukaryote', 'organelle'],
                      ['Biological macromolecules: lipids']),
                    c('Organelles and compartmentalisation',
                      'Each organelle specialises in one job, and a cell can do only what its '
                      'organelles allow.',
                      ['organelle', 'mitochondrion', 'ribosome'],
                      ['Cell structure: prokaryotic and eukaryotic']),
                    c('Endosymbiosis',
                      'Mitochondria and chloroplasts descend from engulfed bacteria, which explains '
                      'their own DNA and double membrane.',
                      ['endosymbiosis', 'mitochondria', 'chloroplast'],
                      ['Organelles and compartmentalisation']),
                    c('Cell size and surface area to volume ratio',
                      'As a cell grows its surface area to volume ratio falls, which limits how '
                      'large it can be.',
                      ['surface area', 'volume', 'ratio'],
                      ['Organelles and compartmentalisation']),
                    c('Cell specialisation and differentiation',
                      'Every cell of an organism shares the same DNA, so differentiation is about '
                      'which genes are expressed.',
                      ['specialisation', 'differentiation', 'gene expression'],
                      ['Cell size and surface area to volume ratio']),
                    c('Microscopy and the study of cells',
                      'Magnification and resolution are different limits, and resolution is what '
                      'actually restricts detail.',
                      ['microscopy', 'magnification', 'resolution'],
                      ['Cell structure: prokaryotic and eukaryotic']),
                ]},
            ]},
            {'unit': 'Membranes and transport', 'prerequisites': ['Cell architecture'], 'topics': [
                {'topic': 'Movement across membranes', 'concepts': [
                    c('Cell membrane structure',
                      'The fluid mosaic model explains selective permeability as proteins embedded '
                      'in a moving lipid bilayer.',
                      ['fluid mosaic', 'bilayer', 'selective permeability'],
                      ['Biological macromolecules: lipids']),
                    c('Passive transport and diffusion',
                      'Net movement down a gradient needs no energy, and its rate depends on the '
                      'gradient, distance and temperature.',
                      ['diffusion', 'concentration gradient', 'passive transport'],
                      ['Cell membrane structure']),
                    c('Osmosis and water potential',
                      'Water moves toward lower water potential, which is why cells shrink or '
                      'burst in different solutions.',
                      ['osmosis', 'water potential', 'turgor'],
                      ['Passive transport and diffusion']),
                    c('Facilitated diffusion and channel proteins',
                      'Polar and charged solutes cross through specific proteins down their '
                      'gradient, with no energy cost.',
                      ['facilitated diffusion', 'channel protein', 'carrier'],
                      ['Passive transport and diffusion']),
                    c('Active transport',
                      'Moving a substance against its gradient costs energy, which is why it stops '
                      'when respiration stops.',
                      ['active transport', 'ATP', 'sodium-potassium pump'],
                      ['Osmosis and water potential']),
                    c('Bulk transport: endocytosis and exocytosis',
                      'Vesicles move large particles in and out, which is how a cell moves material '
                      'the membrane cannot pass.',
                      ['endocytosis', 'exocytosis', 'vesicle'],
                      ['Active transport']),
                ]},
            ]},
        ]},
        {'strand': 'Cellular Energetics', 'units': [
            {'unit': 'Energy and metabolism', 'prerequisites': ['Membranes and transport'],
             'topics': [
                {'topic': 'Coupling energy to work', 'concepts': [
                    c('Energy, metabolism and free energy',
                      'Free-energy change decides whether a reaction can proceed spontaneously.',
                      ['free energy', 'metabolism', 'spontaneous'],
                      ['Active transport']),
                    c('ATP and energy coupling',
                      'ATP transfers a phosphate group, coupling an energy-releasing reaction to '
                      'one that needs energy.',
                      ['ATP', 'energy coupling', 'phosphorylation'],
                      ['Energy, metabolism and free energy']),
                    c('Coupled reactions and metabolic pathways',
                      'Metabolism is a set of enzyme-catalysed steps, each coupled to the next.',
                      ['metabolic pathway', 'anabolism', 'catabolism'],
                      ['ATP and energy coupling']),
                ]},
            ]},
            {'unit': 'Respiration and photosynthesis', 'prerequisites': ['Energy and metabolism'],
             'topics': [
                {'topic': 'Harvesting and capturing energy', 'concepts': [
                    c('Glycolysis',
                      'Glucose splits into pyruvate with a small net gain of ATP and reduced '
                      'electron carriers.',
                      ['glycolysis', 'pyruvate', 'NADH'],
                      ['Coupled reactions and metabolic pathways']),
                    c('The Krebs cycle',
                      'Acetyl-CoA is oxidised completely, releasing carbon dioxide and loading '
                      'electron carriers.',
                      ['Krebs cycle', 'citric acid cycle', 'acetyl-CoA'],
                      ['Glycolysis']),
                    c('Oxidative phosphorylation and the electron transport chain',
                      'Electron transport pumps protons, and the resulting gradient drives ATP '
                      'synthase.',
                      ['electron transport chain', 'chemiosmosis', 'ATP synthase'],
                      ['The Krebs cycle']),
                    c('Fermentation',
                      'Without oxygen, cells regenerate the electron carrier using an organic '
                      'molecule and gain far less ATP.',
                      ['fermentation', 'anaerobic', 'lactate'],
                      ['Glycolysis']),
                    c('Photosynthesis: light-dependent reactions',
                      'Light energy splits water, releasing oxygen and producing ATP and reduced '
                      'carriers.',
                      ['light reactions', 'photosystem', 'photolysis'],
                      ['Oxidative phosphorylation and the electron transport chain']),
                    c('Photosynthesis: the Calvin cycle',
                      'ATP and reduced carriers fix carbon dioxide into sugar using the enzyme '
                      'rubisco.',
                      ['Calvin cycle', 'carbon fixation', 'rubisco'],
                      ['Photosynthesis: light-dependent reactions']),
                    c('Factors affecting photosynthesis and respiration',
                      'Light intensity, carbon dioxide, temperature and oxygen availability each '
                      'limit the rate.',
                      ['limiting factor', 'photosynthesis rate'],
                      ['Photosynthesis: the Calvin cycle']),
                ]},
            ]},
        ]},
        {'strand': 'Cell Communication and Cell Cycle', 'units': [
            {'unit': 'Signal transduction', 'prerequisites': ['Respiration and photosynthesis'],
             'topics': [
                {'topic': 'How cells talk', 'concepts': [
                    c('Signal transduction pathways',
                      'A signal is received, transduced through a cascade and converted into a '
                      'cellular response.',
                      ['signal transduction', 'reception', 'response'],
                      ['Factors affecting photosynthesis and respiration']),
                    c('Receptors and ligands',
                      'A ligand binds a specific receptor, and the receptor type decides whether '
                      'the cell changes fast or slowly.',
                      ['receptor', 'ligand', 'specificity'],
                      ['Signal transduction pathways']),
                    c('Signal amplification and second messengers',
                      'A cascade multiplies the signal so a few molecules produce a large response.',
                      ['second messenger', 'amplification', 'cAMP'],
                      ['Receptors and ligands']),
                    c('Feedback and homeostasis',
                      'Negative feedback opposes a change while positive feedback amplifies it.',
                      ['negative feedback', 'positive feedback', 'homeostasis'],
                      ['Signal transduction pathways']),
                ]},
            ]},
            {'unit': 'The cell cycle', 'prerequisites': ['Signal transduction'], 'topics': [
                {'topic': 'Division and control', 'concepts': [
                    c('The cell cycle and its regulation',
                      'Growth, synthesis and division are ordered phases policed by checkpoints.',
                      ['cell cycle', 'interphase', 'checkpoint'],
                      ['Feedback and homeostasis']),
                    c('Mitosis',
                      'Mitosis produces genetically identical cells for growth and repair.',
                      ['mitosis', 'chromosome', 'identical cells'],
                      ['The cell cycle and its regulation']),
                    c('Checkpoints and cancer',
                      'Failure of cell-cycle control lets damaged cells divide unchecked.',
                      ['cancer', 'checkpoint', 'oncogene'],
                      ['Mitosis']),
                    c('Apoptosis',
                      'Programmed cell death removes damaged or unneeded cells as a normal part of '
                      'development.',
                      ['apoptosis', 'programmed cell death'],
                      ['Checkpoints and cancer']),
                    c('Meiosis',
                      'Meiosis halves the chromosome number and reshuffles genes, creating genetic '
                      'variation.',
                      ['meiosis', 'haploid', 'crossing over'],
                      ['Mitosis']),
                    c('Genetic variation in meiosis',
                      'Independent assortment and crossing over make each gamete genetically '
                      'distinct.',
                      ['independent assortment', 'crossing over', 'variation'],
                      ['Meiosis']),
                ]},
            ]},
        ]},
        {'strand': 'Heredity', 'units': [
            {'unit': 'Patterns of inheritance', 'prerequisites': ['The cell cycle'], 'topics': [
                {'topic': 'From genes to traits', 'concepts': [
                    c('Mendelian inheritance',
                      'Alleles segregate and assort independently, which predicts the ratios of '
                      'offspring phenotypes.',
                      ['Mendel', 'allele', 'segregation'],
                      ['Genetic variation in meiosis']),
                    c('Monohybrid and dihybrid crosses',
                      'Punnett squares predict offspring ratios from parental genotypes.',
                      ['monohybrid', 'dihybrid', 'Punnett square'],
                      ['Mendelian inheritance']),
                    c('Probability in genetics',
                      'Inheritance follows probability rules, so larger samples approach predicted '
                      'ratios.',
                      ['probability', 'chi-square', 'ratio'],
                      ['Monohybrid and dihybrid crosses']),
                    c('Non-Mendelian inheritance',
                      'Incomplete dominance, codominance and multiple alleles produce phenotypes '
                      'that simple dominance cannot explain.',
                      ['incomplete dominance', 'codominance', 'multiple alleles'],
                      ['Mendelian inheritance']),
                    c('Sex-linked inheritance',
                      'Genes on the sex chromosomes produce different inheritance patterns in '
                      'males and females.',
                      ['sex-linked', 'X chromosome', 'carrier'],
                      ['Non-Mendelian inheritance']),
                    c('Pedigrees and inheritance analysis',
                      'A pedigree traces a trait through a family and can reveal its mode of '
                      'inheritance.',
                      ['pedigree', 'inheritance pattern'],
                      ['Sex-linked inheritance']),
                ]},
            ]},
            {'unit': 'Chromosomes and recombination', 'prerequisites': ['Patterns of inheritance'],
             'topics': [
                {'topic': 'Beyond single genes', 'concepts': [
                    c('Chromosomal inheritance',
                      'Genes are carried on chromosomes, so chromosome behaviour explains '
                      'inheritance patterns.',
                      ['chromosome', 'linkage'],
                      ['Pedigrees and inheritance analysis']),
                    c('Linked genes and recombination',
                      'Genes close together on a chromosome tend to be inherited together, and '
                      'recombination frequency measures distance.',
                      ['linked genes', 'recombination', 'map unit'],
                      ['Chromosomal inheritance']),
                    c('Environmental effects on phenotype',
                      'The phenotype is the product of genotype and environment, so identical '
                      'genotypes can differ.',
                      ['phenotype', 'environment', 'gene expression'],
                      ['Non-Mendelian inheritance']),
                ]},
            ]},
        ]},
        {'strand': 'Gene Expression and Regulation', 'units': [
            {'unit': 'From DNA to protein', 'prerequisites': ['Chromosomes and recombination'],
             'topics': [
                {'topic': 'The central dogma', 'concepts': [
                    c('DNA structure and replication',
                      'Complementary base pairing allows semi-conservative replication with '
                      'proofreading.',
                      ['DNA replication', 'semiconservative', 'base pairing'],
                      ['Chromosomal inheritance']),
                    c('Transcription',
                      'RNA polymerase makes an RNA copy of a gene, which is the first step of '
                      'expression.',
                      ['transcription', 'RNA polymerase', 'mRNA'],
                      ['DNA structure and replication']),
                    c('RNA processing',
                      'Eukaryotic RNA is capped, spliced and tailed before it leaves the nucleus.',
                      ['RNA splicing', 'intron', 'exon'],
                      ['Transcription']),
                    c('Translation',
                      'Ribosomes read codons and assemble amino acids into a polypeptide.',
                      ['translation', 'ribosome', 'tRNA'],
                      ['RNA processing']),
                    c('The genetic code',
                      'Codons are redundant but unambiguous, which limits the effect of some '
                      'mutations.',
                      ['genetic code', 'codon', 'redundancy'],
                      ['Translation']),
                ]},
            ]},
            {'unit': 'Regulation and biotechnology', 'prerequisites': ['From DNA to protein'],
             'topics': [
                {'topic': 'Controlling expression', 'concepts': [
                    c('Gene regulation in prokaryotes',
                      'Operons let bacteria switch whole pathways on and off in response to the '
                      'environment.',
                      ['operon', 'lac operon', 'repressor'],
                      ['The genetic code']),
                    c('Gene regulation in eukaryotes',
                      'Eukaryotes regulate at transcription, RNA processing, translation and after '
                      'translation.',
                      ['eukaryotic regulation', 'transcription factor', 'chromatin'],
                      ['Gene regulation in prokaryotes']),
                    c('Mutations',
                      'Substitutions, insertions and deletions change protein sequence, and '
                      'frameshifts are usually more damaging.',
                      ['mutation', 'frameshift', 'substitution'],
                      ['The genetic code']),
                    c('Biotechnology and genetic engineering',
                      'Restriction enzymes, PCR, gel electrophoresis and sequencing let genes be '
                      'read and manipulated.',
                      ['PCR', 'gel electrophoresis', 'recombinant DNA'],
                      ['Gene regulation in eukaryotes']),
                    c('Genome evolution',
                      'Genomes change through duplication, rearrangement and horizontal transfer '
                      'over long timescales.',
                      ['genome', 'gene duplication', 'horizontal transfer'],
                      ['Mutations']),
                ]},
            ]},
        ]},
        {'strand': 'Natural Selection', 'units': [
            {'unit': 'Evolution by natural selection', 'prerequisites': ['Regulation and biotechnology'],
             'topics': [
                {'topic': 'Mechanisms of change', 'concepts': [
                    c('Natural selection and adaptation',
                      'Heritable variation plus differential reproduction changes trait frequencies '
                      'across generations.',
                      ['natural selection', 'adaptation', 'fitness'],
                      ['Mutations']),
                    c('Evidence for evolution',
                      'Fossils, biogeography, comparative anatomy and molecular data converge on '
                      'common descent.',
                      ['fossil record', 'homology', 'biogeography'],
                      ['Natural selection and adaptation']),
                    c('Artificial selection',
                      'Selective breeding shows how quickly allele frequencies shift under strong '
                      'selection.',
                      ['artificial selection', 'selective breeding'],
                      ['Natural selection and adaptation']),
                    c('Population genetics and allele frequencies',
                      'Evolution is a change in allele frequency in a population over time.',
                      ['allele frequency', 'gene pool', 'population genetics'],
                      ['Natural selection and adaptation']),
                    c('Hardy-Weinberg equilibrium',
                      'The null model predicts constant allele frequencies when no evolutionary '
                      'force acts.',
                      ['Hardy-Weinberg', 'equilibrium', 'null model'],
                      ['Population genetics and allele frequencies']),
                    c('Genetic drift and gene flow',
                      'Chance and migration change allele frequencies without any fitness '
                      'advantage.',
                      ['genetic drift', 'gene flow', 'bottleneck'],
                      ['Hardy-Weinberg equilibrium']),
                    c('Speciation',
                      'Reproductive isolation, often after geographic separation, produces new '
                      'species.',
                      ['speciation', 'reproductive isolation', 'allopatric'],
                      ['Genetic drift and gene flow']),
                    c('Phylogeny and classification',
                      'Shared derived characters build a tree of relationships among lineages.',
                      ['phylogeny', 'cladistics', 'common ancestor'],
                      ['Evidence for evolution']),
                    c('Extinction and biodiversity',
                      'Background and mass extinctions shape the diversity of life, and current '
                      'rates are unusually high.',
                      ['extinction', 'biodiversity', 'mass extinction'],
                      ['Speciation']),
                ]},
            ]},
        ]},
        {'strand': 'Ecology', 'units': [
            {'unit': 'Populations and communities', 'prerequisites': ['Evolution by natural selection'],
             'topics': [
                {'topic': 'How organisms interact', 'concepts': [
                    c('Population ecology',
                      'Population size is set by births, deaths, immigration and emigration, and by '
                      'density-dependent limits.',
                      ['population', 'carrying capacity', 'density dependence'],
                      ['Extinction and biodiversity']),
                    c('Population growth models',
                      'Exponential growth assumes unlimited resources while logistic growth '
                      'approaches a carrying capacity.',
                      ['exponential growth', 'logistic growth', 'carrying capacity'],
                      ['Population ecology']),
                    c('Species interactions',
                      'Competition, predation, mutualism and parasitism each change the fitness of '
                      'the interacting species.',
                      ['competition', 'predation', 'mutualism'],
                      ['Population growth models']),
                    c('Community ecology',
                      'Species diversity and structure emerge from interactions and disturbance '
                      'regimes.',
                      ['community', 'diversity', 'keystone species'],
                      ['Species interactions']),
                ]},
            ]},
            {'unit': 'Ecosystems and the biosphere', 'prerequisites': ['Populations and communities'],
             'topics': [
                {'topic': 'Energy and matter in ecosystems', 'concepts': [
                    c('Energy flow and trophic levels',
                      'Energy transfer between trophic levels is inefficient, which limits food '
                      'chain length.',
                      ['trophic level', 'energy pyramid', 'ten per cent rule'],
                      ['Community ecology']),
                    c('Biogeochemical cycles',
                      'Carbon, nitrogen, phosphorus and water cycle between organisms and the '
                      'environment.',
                      ['carbon cycle', 'nitrogen cycle', 'biogeochemical'],
                      ['Energy flow and trophic levels']),
                    c('Ecosystem dynamics and succession',
                      'Disturbance drives succession, and ecosystems differ in how quickly they '
                      'recover.',
                      ['succession', 'resilience', 'disturbance'],
                      ['Biogeochemical cycles']),
                    c('Biodiversity and conservation',
                      'Biodiversity has genetic, species and ecosystem components, each with its '
                      'own threats.',
                      ['biodiversity', 'conservation', 'habitat loss'],
                      ['Ecosystem dynamics and succession']),
                    c('Human impact on ecosystems',
                      'Habitat loss, climate change, pollution and invasive species are the main '
                      'drivers of biodiversity loss.',
                      ['climate change', 'pollution', 'invasive species'],
                      ['Biodiversity and conservation']),
                    c('Behavioural ecology',
                      'Foraging, mating and social behaviour can be analysed by their effect on '
                      'fitness.',
                      ['behavioural ecology', 'optimal foraging', 'kin selection'],
                      ['Species interactions']),
                ]},
            ]},
        ]},
    ],
}


# ================================================================ AP Chemistry
AP_CHEMISTRY = {
    'id': 'ap_chemistry',
    'title': 'AP Chemistry',
    'subject': 'Chemistry',
    'subject_kind': 'science',
    'expected_weeks': 34,
    'description': ('The AP Chemistry course framework: atomic structure and properties, compound '
                    'structure and properties, properties of substances and mixtures, chemical '
                    'reactions, kinetics, thermodynamics, equilibrium, acids and bases, and '
                    'applications of thermodynamics.'),
    'course': 'AP Chemistry - Structure, Reactions and Thermodynamics',
    'strands': [
        {'strand': 'Atomic Structure and Properties', 'units': [
            {'unit': 'Atoms and the mole', 'topics': [
                {'topic': 'Moles and atomic structure', 'concepts': [
                    c('Moles and molar mass',
                      'A mole is Avogadro\'s number of particles, which converts between mass and '
                      'number of particles.',
                      ['mole', 'molar mass', 'Avogadro']),
                    c('Isotopes and average atomic mass',
                      'An element\'s atomic mass is the abundance-weighted average of its isotopes.',
                      ['isotope', 'abundance', 'atomic mass'],
                      ['Moles and molar mass']),
                    c('Mass spectrometry',
                      'A mass spectrum measures isotope masses and abundances, which gives atomic '
                      'mass and can identify a molecule.',
                      ['mass spectrometry', 'molecular ion', 'isotope pattern'],
                      ['Isotopes and average atomic mass']),
                    c('The mole and empirical formulae',
                      'Percentage composition converts to a mole ratio, which gives the empirical '
                      'formula.',
                      ['empirical formula', 'percent composition', 'mole ratio'],
                      ['Moles and molar mass']),
                ]},
            ]},
            {'unit': 'Electrons in atoms', 'prerequisites': ['Atoms and the mole'], 'topics': [
                {'topic': 'Electronic structure', 'concepts': [
                    c('Electron configuration',
                      'Electrons fill orbitals in order of energy, following the aufbau principle '
                      'and Hund\'s rule.',
                      ['electron configuration', 'orbital', 'aufbau'],
                      ['The mole and empirical formulae']),
                    c('Photoelectron spectroscopy',
                      'A photoelectron spectrum reports the binding energy of each electron shell '
                      'and subshell.',
                      ['photoelectron spectroscopy', 'binding energy', 'subshell'],
                      ['Electron configuration']),
                    c('Coulomb\'s law and atomic structure',
                      'The attraction between nucleus and electrons depends on charge and '
                      'distance, which explains periodic trends.',
                      ['Coulomb\'s law', 'effective nuclear charge', 'shielding'],
                      ['Electron configuration']),
                    c('Periodic trends',
                      'Atomic radius, ionisation energy, electron affinity and electronegativity '
                      'follow from nuclear charge and shielding.',
                      ['periodic trend', 'ionisation energy', 'electronegativity'],
                      ['Coulomb\'s law and atomic structure']),
                    c('Valence electrons and the periodic table',
                      'Group position gives the valence configuration, which predicts an element\'s '
                      'chemistry.',
                      ['valence electron', 'group', 'periodic table'],
                      ['Periodic trends']),
                ]},
            ]},
        ]},
        {'strand': 'Compound Structure and Properties', 'units': [
            {'unit': 'Bonding and geometry', 'prerequisites': ['Electrons in atoms'], 'topics': [
                {'topic': 'How atoms bond', 'concepts': [
                    c('Types of chemical bonds',
                      'Bonds range from ionic to covalent to metallic, and the type follows from '
                      'electronegativity difference.',
                      ['ionic bond', 'covalent bond', 'metallic bond'],
                      ['Valence electrons and the periodic table']),
                    c('Ionic bonding and lattice energy',
                      'Lattice energy grows with charge and shrinks with ion size, which controls '
                      'melting point and solubility.',
                      ['lattice energy', 'ionic solid', 'Coulomb'],
                      ['Types of chemical bonds']),
                    c('Covalent bonding and Lewis structures',
                      'Lewis structures show shared and lone pairs and predict bond order and '
                      'geometry.',
                      ['Lewis structure', 'lone pair', 'bond order'],
                      ['Types of chemical bonds']),
                    c('Resonance and formal charge',
                      'Resonance spreads electrons over several positions, and formal charge '
                      'selects the best structure.',
                      ['resonance', 'formal charge'],
                      ['Covalent bonding and Lewis structures']),
                    c('VSEPR and molecular geometry',
                      'Electron domains repel and arrange as far apart as possible, which sets the '
                      'shape.',
                      ['VSEPR', 'molecular geometry', 'bond angle'],
                      ['Covalent bonding and Lewis structures']),
                    c('Hybridisation and bonding models',
                      'Mixing atomic orbitals explains observed geometries and bond angles.',
                      ['hybridisation', 'sp', 'sp2', 'sp3'],
                      ['VSEPR and molecular geometry']),
                    c('Polarity and dipole moments',
                      'Polar bonds plus an asymmetric shape produce a net dipole, which controls '
                      'intermolecular forces.',
                      ['polarity', 'dipole moment'],
                      ['VSEPR and molecular geometry']),
                    c('Intermolecular forces',
                      'London dispersion, dipole-dipole and hydrogen bonding set boiling point and '
                      'solubility.',
                      ['intermolecular force', 'hydrogen bond', 'dispersion'],
                      ['Polarity and dipole moments']),
                ]},
            ]},
        ]},
        {'strand': 'Properties of Substances and Mixtures', 'units': [
            {'unit': 'States, gases and solutions', 'prerequisites': ['Bonding and geometry'],
             'topics': [
                {'topic': 'Bulk properties', 'concepts': [
                    c('Solids, liquids and gases',
                      'The kinetic energy of particles relative to intermolecular forces decides '
                      'the state.',
                      ['states of matter', 'kinetic energy'],
                      ['Intermolecular forces']),
                    c('Phase changes and phase diagrams',
                      'Heating and pressure change the balance of phases, which a phase diagram '
                      'maps.',
                      ['phase change', 'phase diagram', 'triple point'],
                      ['Solids, liquids and gases']),
                    c('The ideal gas law',
                      'Pressure, volume, temperature and moles are linked by PV equals nRT.',
                      ['ideal gas law', 'PV=nRT', 'pressure'],
                      ['Solids, liquids and gases']),
                    c('Kinetic molecular theory',
                      'Gas pressure and temperature follow from particle collisions and average '
                      'kinetic energy.',
                      ['kinetic molecular theory', 'collision', 'temperature'],
                      ['The ideal gas law']),
                    c('Deviations from ideal behaviour',
                      'Real gases deviate at high pressure and low temperature, where volume and '
                      'attraction matter.',
                      ['real gas', 'van der Waals', 'deviation'],
                      ['Kinetic molecular theory']),
                    c('Solutions and solubility',
                      'Like dissolves like, and solubility depends on temperature and pressure.',
                      ['solubility', 'solute', 'solvent'],
                      ['Intermolecular forces']),
                    c('Concentration and molarity',
                      'Molarity expresses moles of solute per litre of solution.',
                      ['molarity', 'concentration', 'dilution'],
                      ['Solutions and solubility']),
                    c('Separating mixtures',
                      'Distillation, filtration and chromatography separate by differing physical '
                      'properties.',
                      ['distillation', 'chromatography', 'filtration'],
                      ['Concentration and molarity']),
                    c('Colligative properties',
                      'Vapour pressure, boiling point, freezing point and osmosis depend on '
                      'particle count, not identity.',
                      ['colligative', 'boiling point elevation', 'osmotic pressure'],
                      ['Concentration and molarity']),
                    c('Spectrophotometry and the Beer-Lambert law',
                      'Absorbance is proportional to concentration and path length, which allows '
                      'concentration to be measured.',
                      ['Beer-Lambert', 'absorbance', 'spectrophotometry'],
                      ['Concentration and molarity']),
                ]},
            ]},
        ]},
        {'strand': 'Chemical Reactions', 'units': [
            {'unit': 'Reaction types and stoichiometry', 'prerequisites': ['States, gases and solutions'],
             'topics': [
                {'topic': 'Writing and using reactions', 'concepts': [
                    c('Writing and balancing equations',
                      'Atoms are conserved, so coefficients must balance every element.',
                      ['balancing', 'chemical equation', 'conservation'],
                      ['Concentration and molarity']),
                    c('Types of reactions',
                      'Synthesis, decomposition, combustion, precipitation and neutralisation '
                      'predict products.',
                      ['reaction type', 'precipitation', 'combustion'],
                      ['Writing and balancing equations']),
                    c('Net ionic equations',
                      'Spectator ions are removed to show the species that actually change.',
                      ['net ionic equation', 'spectator ion', 'precipitate'],
                      ['Types of reactions']),
                    c('Stoichiometry and limiting reactants',
                      'Mole ratios from the balanced equation give theoretical yield, and the '
                      'limiting reactant caps it.',
                      ['stoichiometry', 'limiting reactant', 'theoretical yield'],
                      ['Writing and balancing equations']),
                    c('Percent yield',
                      'Comparing actual with theoretical yield measures how complete and selective '
                      'a reaction is.',
                      ['percent yield', 'actual yield'],
                      ['Stoichiometry and limiting reactants']),
                    c('Acid-base reactions',
                      'Proton transfer reactions neutralise acids and bases and can be followed by '
                      'titration.',
                      ['acid-base', 'neutralisation', 'proton transfer'],
                      ['Types of reactions']),
                    c('Oxidation-reduction reactions',
                      'Electron transfer changes oxidation states, and half-reactions separate the '
                      'two processes.',
                      ['redox', 'oxidation state', 'half-reaction'],
                      ['Net ionic equations']),
                    c('Titration',
                      'A titration uses a known concentration to find an unknown one at the '
                      'equivalence point.',
                      ['titration', 'equivalence point', 'indicator'],
                      ['Acid-base reactions']),
                ]},
            ]},
        ]},
        {'strand': 'Kinetics', 'units': [
            {'unit': 'Reaction rates', 'prerequisites': ['Reaction types and stoichiometry'],
             'topics': [
                {'topic': 'How fast reactions go', 'concepts': [
                    c('Reaction rate',
                      'Rate is the change in concentration of a reactant or product per unit time.',
                      ['reaction rate', 'concentration change'],
                      ['Stoichiometry and limiting reactants']),
                    c('Rate laws and reaction order',
                      'The rate law is determined by experiment, and its orders need not match the '
                      'stoichiometric coefficients.',
                      ['rate law', 'reaction order', 'rate constant'],
                      ['Reaction rate']),
                    c('Determining rate laws from data',
                      'Initial-rate and graphical methods extract orders and the rate constant.',
                      ['initial rate', 'method of initial rates'],
                      ['Rate laws and reaction order']),
                    c('Integrated rate laws and half-life',
                      'Integrating the rate law gives concentration against time and the '
                      'half-life for each order.',
                      ['integrated rate law', 'half-life', 'first order'],
                      ['Determining rate laws from data']),
                    c('Collision theory and activation energy',
                      'Molecules must collide with enough energy and the right orientation to '
                      'react.',
                      ['collision theory', 'activation energy', 'orientation'],
                      ['Reaction rate']),
                    c('The Arrhenius equation',
                      'Rate constants rise with temperature in a way that reveals activation '
                      'energy.',
                      ['Arrhenius', 'activation energy', 'temperature dependence'],
                      ['Collision theory and activation energy']),
                    c('Reaction mechanisms',
                      'A mechanism is a sequence of elementary steps whose slowest step sets the '
                      'overall rate.',
                      ['mechanism', 'elementary step', 'rate-determining step'],
                      ['Collision theory and activation energy']),
                    c('Catalysis',
                      'A catalyst provides a lower-energy path without being consumed, so it '
                      'raises rate not yield.',
                      ['catalyst', 'homogeneous', 'heterogeneous'],
                      ['Reaction mechanisms']),
                ]},
            ]},
        ]},
        {'strand': 'Thermodynamics', 'units': [
            {'unit': 'Energy and enthalpy', 'prerequisites': ['Reaction rates'], 'topics': [
                {'topic': 'Heat, work and enthalpy', 'concepts': [
                    c('Endothermic and exothermic processes',
                      'Energy is absorbed or released, and the sign of enthalpy change reports '
                      'which.',
                      ['endothermic', 'exothermic', 'enthalpy'],
                      ['Reaction mechanisms']),
                    c('Heat capacity and calorimetry',
                      'Calorimetry measures heat exchanged using mass, specific heat and '
                      'temperature change.',
                      ['calorimetry', 'specific heat', 'heat capacity'],
                      ['Endothermic and exothermic processes']),
                    c('Enthalpy of reaction and Hess\'s law',
                      'Enthalpy is a state function, so reactions can be added to find an unknown '
                      'enthalpy.',
                      ['Hess\'s law', 'state function', 'enthalpy of reaction'],
                      ['Heat capacity and calorimetry']),
                    c('Bond enthalpies',
                      'Breaking bonds costs energy and forming bonds releases it, which gives an '
                      'estimate of reaction enthalpy.',
                      ['bond enthalpy', 'bond breaking'],
                      ['Enthalpy of reaction and Hess\'s law']),
                    c('Entropy',
                      'Entropy measures dispersal of energy and matter, and it tends to increase.',
                      ['entropy', 'disorder', 'second law'],
                      ['Enthalpy of reaction and Hess\'s law']),
                    c('Gibbs free energy',
                      'Free energy combines enthalpy and entropy to decide thermodynamic '
                      'favorability.',
                      ['Gibbs free energy', 'spontaneity'],
                      ['Entropy']),
                ]},
            ]},
        ]},
        {'strand': 'Equilibrium', 'units': [
            {'unit': 'Dynamic equilibrium', 'prerequisites': ['Energy and enthalpy'], 'topics': [
                {'topic': 'Reversible reactions', 'concepts': [
                    c('Dynamic equilibrium',
                      'Forward and reverse rates become equal, so concentrations stop changing '
                      'while reactions continue.',
                      ['dynamic equilibrium', 'reversible reaction'],
                      ['Gibbs free energy']),
                    c('The equilibrium constant K',
                      'K expresses the ratio of products to reactants at equilibrium and its size '
                      'reports the extent of reaction.',
                      ['equilibrium constant', 'K'],
                      ['Dynamic equilibrium']),
                    c('The reaction quotient Q',
                      'Comparing Q with K predicts the direction a system must shift to reach '
                      'equilibrium.',
                      ['reaction quotient', 'Q', 'direction of shift'],
                      ['The equilibrium constant K']),
                    c('Le Chatelier\'s principle',
                      'A system at equilibrium shifts to partially oppose a change in '
                      'concentration, pressure or temperature.',
                      ['Le Chatelier', 'stress', 'shift'],
                      ['The reaction quotient Q']),
                    c('Calculating equilibrium concentrations',
                      'ICE tables track initial, change and equilibrium amounts to solve for '
                      'concentrations.',
                      ['ICE table', 'equilibrium concentration'],
                      ['The equilibrium constant K']),
                    c('Solubility equilibria and Ksp',
                      'A solubility product describes the equilibrium between a solid and its ions.',
                      ['Ksp', 'solubility product', 'common ion'],
                      ['Calculating equilibrium concentrations']),
                    c('Free energy and equilibrium',
                      'The standard free-energy change is related to K, which links thermodynamics '
                      'and equilibrium.',
                      ['free energy', 'equilibrium constant', 'K'],
                      ['Gibbs free energy']),
                ]},
            ]},
        ]},
        {'strand': 'Acids and Bases', 'units': [
            {'unit': 'Proton transfer in water', 'prerequisites': ['Dynamic equilibrium'], 'topics': [
                {'topic': 'Acidity and pH', 'concepts': [
                    c('Acid-base definitions',
                      'Brønsted-Lowry acids donate protons and bases accept them, and Lewis '
                      'definitions generalise to electron pairs.',
                      ['Brønsted-Lowry', 'Lewis acid', 'proton'],
                      ['Free energy and equilibrium']),
                    c('pH and pOH',
                      'pH is the negative logarithm of hydrogen-ion concentration, and pH plus pOH '
                      'is fourteen at 25 degrees.',
                      ['pH', 'pOH', 'logarithm'],
                      ['Acid-base definitions']),
                    c('Strong acids and bases',
                      'Strong acids and bases ionise completely, so concentration directly gives '
                      'the ion concentration.',
                      ['strong acid', 'strong base', 'complete ionisation'],
                      ['pH and pOH']),
                    c('Weak acid and base equilibria',
                      'Weak acids ionise partially, so an equilibrium calculation is needed.',
                      ['weak acid', 'Ka', 'percent ionisation'],
                      ['Strong acids and bases']),
                    c('Ka, Kb and conjugate pairs',
                      'Ka and Kb of a conjugate pair multiply to the ion product of water.',
                      ['Ka', 'Kb', 'conjugate pair', 'Kw'],
                      ['Weak acid and base equilibria']),
                    c('Molecular structure and acid strength',
                      'Bond polarity and stability of the conjugate base explain why some acids are '
                      'stronger.',
                      ['acid strength', 'inductive effect', 'conjugate base'],
                      ['Ka, Kb and conjugate pairs']),
                ]},
            ]},
            {'unit': 'Buffers and titrations', 'prerequisites': ['Proton transfer in water'], 'topics': [
                {'topic': 'Controlling pH', 'concepts': [
                    c('Buffers',
                      'A weak acid and its conjugate base resist pH change by neutralising added '
                      'acid or base.',
                      ['buffer', 'conjugate base', 'pH resistance'],
                      ['Ka, Kb and conjugate pairs']),
                    c('The Henderson-Hasselbalch equation',
                      'pH depends on pKa and the ratio of conjugate base to acid, which is the '
                      'buffer calculation.',
                      ['Henderson-Hasselbalch', 'pKa', 'buffer ratio'],
                      ['Buffers']),
                    c('Acid-base titration curves',
                      'A titration curve\'s shape and equivalence pH depend on the strength of the '
                      'acid and base.',
                      ['titration curve', 'equivalence point', 'half-equivalence'],
                      ['Strong acids and bases']),
                    c('Buffer capacity and selection',
                      'A buffer works best near its pKa and within a limited capacity.',
                      ['buffer capacity', 'pKa', 'selection'],
                      ['The Henderson-Hasselbalch equation']),
                ]},
            ]},
        ]},
        {'strand': 'Applications of Thermodynamics', 'units': [
            {'unit': 'Electrochemistry', 'prerequisites': ['Buffers and titrations'], 'topics': [
                {'topic': 'Electrons doing work', 'concepts': [
                    c('Galvanic cells',
                      'A spontaneous redox reaction separated into half-cells produces a voltage.',
                      ['galvanic cell', 'half-cell', 'anode', 'cathode'],
                      ['Buffer capacity and selection']),
                    c('Cell potential and standard reduction potentials',
                      'Standard reduction potentials give the cell potential as cathode minus '
                      'anode.',
                      ['standard reduction potential', 'cell potential', 'EMF'],
                      ['Galvanic cells']),
                    c('Free energy and cell potential',
                      'Cell potential is proportional to the free-energy change of the reaction.',
                      ['free energy', 'cell potential', 'faraday'],
                      ['Cell potential and standard reduction potentials']),
                    c('The Nernst equation',
                      'Non-standard concentrations change cell potential in a way the Nernst '
                      'equation predicts.',
                      ['Nernst equation', 'concentration cell'],
                      ['Free energy and cell potential']),
                    c('Electrolytic cells',
                      'A non-spontaneous reaction can be driven by an external voltage.',
                      ['electrolytic cell', 'electrolysis', 'overpotential'],
                      ['Cell potential and standard reduction potentials']),
                    c('Faraday\'s laws and quantitative electrolysis',
                      'Charge passed relates to moles of electrons and so to mass deposited.',
                      ['Faraday', 'electrolysis', 'charge'],
                      ['Electrolytic cells']),
                ]},
            ]},
        ]},
    ],
}


# ==================================================================== Algebra 2
ALGEBRA_2 = {
    'id': 'algebra_2',
    'title': 'Algebra 2',
    'subject': 'Mathematics',
    'subject_kind': 'mathematics',
    'expected_weeks': 36,
    'description': ('A full-year Algebra 2 course: polynomial and rational functions, complex '
                    'numbers, exponents, radicals and logarithms, transformations, trigonometry, '
                    'conic sections, sequences and series, probability and matrices.'),
    'course': 'Algebra 2 - Functions, Logarithms, Trigonometry and Series',
    'strands': [
        {'strand': 'Polynomials', 'units': [
            {'unit': 'Polynomial arithmetic and factoring', 'topics': [
                {'topic': 'Working with polynomials', 'concepts': [
                    c('Polynomials and their degree',
                      'A polynomial is a sum of power terms, and its degree governs its end '
                      'behaviour and how many roots it can have.',
                      ['polynomial', 'degree', 'leading coefficient']),
                    c('Adding and subtracting polynomials',
                      'Like terms combine by their power, so addition and subtraction act on '
                      'coefficients of the same degree.',
                      ['like terms', 'polynomial addition'],
                      ['Polynomials and their degree']),
                    c('Multiplying polynomials',
                      'Every term of one polynomial multiplies every term of the other, which is '
                      'the distributive property applied repeatedly.',
                      ['polynomial multiplication', 'distribution'],
                      ['Adding and subtracting polynomials']),
                    c('Special polynomial products',
                      'Perfect-square and difference-of-squares patterns let products be written '
                      'without full distribution.',
                      ['perfect square', 'difference of squares'],
                      ['Multiplying polynomials']),
                    c('Factoring common factors',
                      'Removing the greatest common factor is the first step of every '
                      'factorisation.',
                      ['greatest common factor', 'factoring'],
                      ['Multiplying polynomials']),
                ]},
            ]},
            {'unit': 'Polynomial factorisation and division', 'prerequisites': ['Polynomial arithmetic and factoring'],
             'topics': [
                {'topic': 'Finding factors and zeros', 'concepts': [
                    c('Factoring by grouping',
                      'Grouping pairs of terms with a shared factor turns a four-term polynomial '
                      'into a product.',
                      ['factoring by grouping', 'common binomial'],
                      ['Factoring common factors']),
                    c('Factoring quadratics',
                      'A quadratic factors into two linear factors whose constants satisfy the sum '
                      'and product conditions.',
                      ['quadratic', 'factor pair', 'sum and product'],
                      ['Factoring by grouping']),
                    c('Factoring sum and difference of cubes',
                      'Sum and difference of cubes factor into a binomial and a quadratic using '
                      'standard patterns.',
                      ['sum of cubes', 'difference of cubes'],
                      ['Special polynomial products']),
                    c('The factor theorem',
                      'A polynomial has a factor x minus c exactly when its value at c is zero.',
                      ['factor theorem', 'zero of a polynomial'],
                      ['Factoring quadratics']),
                    c('The remainder theorem',
                      'The remainder on dividing by x minus c equals the polynomial\'s value at c.',
                      ['remainder theorem', 'synthetic substitution'],
                      ['The factor theorem']),
                    c('Long division of polynomials',
                      'Polynomial long division mirrors integer long division and produces a '
                      'quotient and a remainder.',
                      ['polynomial long division', 'quotient', 'remainder'],
                      ['The remainder theorem']),
                    c('Synthetic division',
                      'Synthetic division divides by a linear factor quickly using only '
                      'coefficients.',
                      ['synthetic division', 'linear factor'],
                      ['Long division of polynomials']),
                    c('Factoring higher-degree polynomials',
                      'Combining the factor theorem, division and pattern recognition factors '
                      'polynomials of any degree.',
                      ['higher-degree polynomial', 'rational root theorem'],
                      ['Synthetic division']),
                ]},
            ]},
            {'unit': 'Polynomial graphs', 'prerequisites': ['Polynomial factorisation and division'],
             'topics': [
                {'topic': 'Shape and zeros', 'concepts': [
                    c('End behaviour of polynomials',
                      'The leading term decides what the graph does as the input grows large in '
                      'either direction.',
                      ['end behaviour', 'leading term'],
                      ['Factoring higher-degree polynomials']),
                    c('Zeros and multiplicity',
                      'A repeated root makes the graph touch or flatten at the axis instead of '
                      'crossing it.',
                      ['multiplicity', 'zero', 'turning point'],
                      ['End behaviour of polynomials']),
                    c('Graphing polynomial functions',
                      'Zeros, multiplicity, end behaviour and the y-intercept together determine '
                      'the sketch.',
                      ['graphing polynomial', 'y-intercept'],
                      ['Zeros and multiplicity']),
                    c('The intermediate value theorem',
                      'A continuous polynomial takes every value between its endpoint values, '
                      'which locates real roots.',
                      ['intermediate value theorem', 'sign change'],
                      ['Graphing polynomial functions']),
                    c('Symmetry in polynomial graphs',
                      'Even and odd symmetry come from the parity of the exponents.',
                      ['even function', 'odd function', 'symmetry'],
                      ['Graphing polynomial functions']),
                ]},
            ]},
        ]},
        {'strand': 'Complex Numbers', 'units': [
            {'unit': 'Extending the number system', 'prerequisites': ['Polynomial graphs'], 'topics': [
                {'topic': 'Imaginary and complex numbers', 'concepts': [
                    c('The imaginary unit i',
                      'The imaginary unit squares to minus one, which gives negative numbers '
                      'square roots.',
                      ['imaginary unit', 'i', 'square root'],
                      ['Symmetry in polynomial graphs']),
                    c('Complex numbers and their arithmetic',
                      'Complex numbers add componentwise and multiply by distributing, treating i '
                      'squared as minus one.',
                      ['complex number', 'real part', 'imaginary part'],
                      ['The imaginary unit i']),
                    c('Complex conjugates',
                      'Multiplying by the conjugate removes the imaginary part, which is how a '
                      'quotient is simplified.',
                      ['complex conjugate', 'modulus'],
                      ['Complex numbers and their arithmetic']),
                    c('Quadratic equations with complex solutions',
                      'A negative discriminant gives a conjugate pair of complex roots.',
                      ['discriminant', 'complex roots'],
                      ['Complex conjugates']),
                    c('The fundamental theorem of algebra',
                      'A degree-n polynomial has exactly n complex roots counted with '
                      'multiplicity.',
                      ['fundamental theorem of algebra', 'roots'],
                      ['Quadratic equations with complex solutions']),
                ]},
            ]},
        ]},
        {'strand': 'Exponentials and Logarithms', 'units': [
            {'unit': 'Rational exponents and radicals', 'prerequisites': ['Extending the number system'],
             'topics': [
                {'topic': 'Roots as powers', 'concepts': [
                    c('Rational exponents',
                      'A fractional exponent is a root, so radicals and powers are two notations '
                      'for the same thing.',
                      ['rational exponent', 'radical'],
                      ['The fundamental theorem of algebra']),
                    c('Simplifying radical expressions',
                      'Radicals simplify by removing perfect-power factors and rationalising '
                      'denominators.',
                      ['radical', 'rationalise', 'simplify'],
                      ['Rational exponents']),
                    c('Radical equations',
                      'Squaring both sides can introduce extraneous solutions, so every result must '
                      'be checked.',
                      ['radical equation', 'extraneous solution'],
                      ['Simplifying radical expressions']),
                    c('Graphing square and cube root functions',
                      'Root graphs have restricted domains and characteristic shapes that '
                      'transform like other functions.',
                      ['square root graph', 'domain restriction'],
                      ['Radical equations']),
                ]},
            ]},
            {'unit': 'Exponential and logarithmic functions', 'prerequisites': ['Rational exponents and radicals'],
             'topics': [
                {'topic': 'Growth, decay and logs', 'concepts': [
                    c('Exponential growth and decay',
                      'A quantity changes by a constant factor per period, which is multiplicative '
                      'rather than additive.',
                      ['exponential growth', 'decay', 'growth factor'],
                      ['Graphing square and cube root functions']),
                    c('Graphing exponential functions',
                      'Exponential graphs have a horizontal asymptote and pass through the point '
                      'zero one.',
                      ['exponential graph', 'asymptote'],
                      ['Exponential growth and decay']),
                    c('The number e and continuous growth',
                      'Continuous compounding leads to the base e, which describes growth as a '
                      'rate.',
                      ['e', 'continuous compounding'],
                      ['Graphing exponential functions']),
                    c('Compound interest',
                      'Compound interest applies the growth factor repeatedly, and more frequent '
                      'compounding raises the effective rate.',
                      ['compound interest', 'effective rate'],
                      ['The number e and continuous growth']),
                    c('Introduction to logarithms',
                      'A logarithm answers the exponent question, and it is the inverse of the '
                      'exponential.',
                      ['logarithm', 'inverse', 'base'],
                      ['Graphing exponential functions']),
                    c('Properties of logarithms',
                      'Products, quotients and powers become sums, differences and multiples of '
                      'logs.',
                      ['log properties', 'product rule', 'power rule'],
                      ['Introduction to logarithms']),
                    c('Solving exponential equations with logarithms',
                      'Taking a logarithm of both sides isolates an unknown exponent.',
                      ['exponential equation', 'logarithm'],
                      ['Properties of logarithms']),
                    c('Solving logarithmic equations',
                      'Rewriting in exponential form solves log equations, and every solution must '
                      'be checked for domain.',
                      ['logarithmic equation', 'domain check'],
                      ['Properties of logarithms']),
                    c('Graphing logarithmic functions',
                      'A log graph is the reflection of its exponential in the line y equals x.',
                      ['logarithmic graph', 'reflection'],
                      ['Introduction to logarithms']),
                    c('Change of base',
                      'Change of base rewrites a logarithm in any base, which makes any log '
                      'computable.',
                      ['change of base', 'logarithm'],
                      ['Properties of logarithms']),
                ]},
            ]},
        ]},
        {'strand': 'Functions', 'units': [
            {'unit': 'Transformations and inverses', 'prerequisites': ['Exponential and logarithmic functions'],
             'topics': [
                {'topic': 'Changing a graph', 'concepts': [
                    c('Function transformations',
                      'Shifts, stretches and reflections move a parent graph without changing its '
                      'shape family.',
                      ['transformation', 'parent function'],
                      ['Graphing logarithmic functions']),
                    c('Shifting and reflecting graphs',
                      'Horizontal changes act inside the function and reverse intuition, while '
                      'vertical changes act outside.',
                      ['shift', 'reflection', 'inside outside'],
                      ['Function transformations']),
                    c('Stretching and compressing graphs',
                      'A factor greater than one stretches and a factor between zero and one '
                      'compresses.',
                      ['stretch', 'compression', 'scale factor'],
                      ['Shifting and reflecting graphs']),
                    c('Even and odd functions',
                      'Even functions are symmetric about the y-axis and odd functions about the '
                      'origin.',
                      ['even function', 'odd function'],
                      ['Function transformations']),
                    c('Inverse functions',
                      'An inverse undoes a function, and it exists only where the function is '
                      'one-to-one.',
                      ['inverse function', 'one-to-one', 'domain'],
                      ['Function transformations']),
                    c('Composite functions',
                      'A composite applies one function to the output of another, and order '
                      'matters.',
                      ['composite function', 'composition'],
                      ['Inverse functions']),
                ]},
            ]},
            {'unit': 'Rational functions', 'prerequisites': ['Transformations and inverses'], 'topics': [
                {'topic': 'Quotients of polynomials', 'concepts': [
                    c('Rational expressions and simplification',
                      'A rational expression is a quotient of polynomials, simplified by cancelling '
                      'common factors.',
                      ['rational expression', 'simplify'],
                      ['Composite functions']),
                    c('Multiplying and dividing rational expressions',
                      'Multiplication and division work like fractions, with factoring first.',
                      ['rational multiplication', 'reciprocal'],
                      ['Rational expressions and simplification']),
                    c('Adding and subtracting rational expressions',
                      'A common denominator is required, exactly as with numerical fractions.',
                      ['common denominator', 'rational addition'],
                      ['Multiplying and dividing rational expressions']),
                    c('Solving rational equations',
                      'Multiplying by the common denominator can introduce extraneous solutions, '
                      'so results must be checked.',
                      ['rational equation', 'extraneous solution'],
                      ['Adding and subtracting rational expressions']),
                    c('Asymptotes and holes',
                      'Vertical asymptotes come from non-cancelled factors and holes from '
                      'cancelled ones.',
                      ['vertical asymptote', 'hole', 'horizontal asymptote'],
                      ['Solving rational equations']),
                    c('Graphing rational functions',
                      'Intercepts, asymptotes and holes together determine the shape of a rational '
                      'graph.',
                      ['rational graph', 'asymptote'],
                      ['Asymptotes and holes']),
                ]},
            ]},
        ]},
        {'strand': 'Equations and Modelling', 'units': [
            {'unit': 'Solving and modelling', 'prerequisites': ['Rational functions'], 'topics': [
                {'topic': 'Choosing and using models', 'concepts': [
                    c('Solving exponential and logarithmic equations',
                      'Choosing the right inverse isolates the unknown in either direction.',
                      ['exponential equation', 'logarithmic equation'],
                      ['Graphing rational functions']),
                    c('Solving systems with nonlinear equations',
                      'Substitution reduces a nonlinear system to one equation in one variable.',
                      ['nonlinear system', 'substitution'],
                      ['Solving exponential and logarithmic equations']),
                    c('Absolute value equations and inequalities',
                      'Absolute value splits into two cases, and inequalities require checking the '
                      'direction.',
                      ['absolute value', 'case split'],
                      ['Solving systems with nonlinear equations']),
                    c('Linear and quadratic models',
                      'Constant difference suggests a linear model and constant second difference '
                      'a quadratic one.',
                      ['linear model', 'quadratic model'],
                      ['Absolute value equations and inequalities']),
                    c('Exponential and logarithmic models',
                      'A constant ratio suggests exponential growth or decay.',
                      ['exponential model', 'decay'],
                      ['Linear and quadratic models']),
                    c('Choosing a model and checking fit',
                      'Residuals and context decide which model is defensible.',
                      ['residual', 'model fit'],
                      ['Exponential and logarithmic models']),
                ]},
            ]},
        ]},
        {'strand': 'Trigonometry', 'units': [
            {'unit': 'Angles and the unit circle', 'prerequisites': ['Solving and modelling'], 'topics': [
                {'topic': 'Circular functions', 'concepts': [
                    c('Angles and radian measure',
                      'Radians measure an angle by arc length, which makes calculus and periodicity '
                      'natural.',
                      ['radian', 'arc length', 'angle'],
                      ['Choosing a model and checking fit']),
                    c('The unit circle',
                      'The unit circle gives sine and cosine as coordinates and extends them beyond '
                      'right triangles.',
                      ['unit circle', 'sine', 'cosine'],
                      ['Angles and radian measure']),
                    c('Sine, cosine and tangent',
                      'The three basic ratios relate the sides of a right triangle and extend to '
                      'any angle.',
                      ['sine', 'cosine', 'tangent', 'SOHCAHTOA'],
                      ['The unit circle']),
                    c('Graphing trigonometric functions',
                      'Amplitude, period, phase and midline describe a transformed sinusoid.',
                      ['amplitude', 'period', 'sinusoid'],
                      ['Sine, cosine and tangent']),
                    c('Trigonometric identities',
                      'Pythagorean, sum and double-angle identities rewrite expressions and prove '
                      'equalities.',
                      ['identity', 'Pythagorean identity', 'double angle'],
                      ['Graphing trigonometric functions']),
                    c('Solving trigonometric equations',
                      'Periodicity means a trigonometric equation usually has infinitely many '
                      'solutions.',
                      ['trigonometric equation', 'periodicity'],
                      ['Trigonometric identities']),
                    c('Inverse trigonometric functions',
                      'Inverse functions recover an angle, restricted to a principal range to stay '
                      'one-to-one.',
                      ['inverse sine', 'principal value', 'range'],
                      ['The unit circle']),
                ]},
            ]},
        ]},
        {'strand': 'Conic Sections, Series and Probability', 'units': [
            {'unit': 'Conic sections', 'prerequisites': ['Angles and the unit circle'], 'topics': [
                {'topic': 'Curves from cones', 'concepts': [
                    c('Parabolas',
                      'A parabola is the set of points equidistant from a focus and a directrix.',
                      ['parabola', 'focus', 'directrix'],
                      ['Inverse trigonometric functions']),
                    c('Circles',
                      'A circle is the set of points a fixed distance from a centre.',
                      ['circle', 'radius', 'completing the square'],
                      ['Parabolas']),
                    c('Ellipses',
                      'An ellipse is the set of points whose distances to two foci sum to a '
                      'constant.',
                      ['ellipse', 'foci', 'major axis'],
                      ['Circles']),
                    c('Hyperbolas',
                      'A hyperbola is the set of points whose distances to two foci differ by a '
                      'constant.',
                      ['hyperbola', 'foci', 'asymptote'],
                      ['Ellipses']),
                    c('Identifying conic sections',
                      'The general second-degree equation is classified by its coefficients.',
                      ['conic classification', 'discriminant'],
                      ['Hyperbolas']),
                ]},
            ]},
            {'unit': 'Sequences, series and counting', 'prerequisites': ['Conic sections'], 'topics': [
                {'topic': 'Discrete patterns', 'concepts': [
                    c('Arithmetic sequences and series',
                      'An arithmetic sequence adds a constant difference and its series sum has a '
                      'closed form.',
                      ['arithmetic sequence', 'common difference', 'series sum'],
                      ['Identifying conic sections']),
                    c('Geometric sequences and series',
                      'A geometric sequence multiplies by a constant ratio, and its finite sum also '
                      'has a closed form.',
                      ['geometric sequence', 'common ratio', 'series sum'],
                      ['Arithmetic sequences and series']),
                    c('Summation notation',
                      'Sigma notation compresses a sum and makes index changes explicit.',
                      ['sigma notation', 'summation index'],
                      ['Geometric sequences and series']),
                    c('Infinite geometric series',
                      'An infinite geometric series converges exactly when the common ratio is '
                      'smaller than one in size.',
                      ['infinite series', 'convergence', 'common ratio'],
                      ['Summation notation']),
                    c('The binomial theorem',
                      'Binomial coefficients from Pascal\'s triangle expand a power of a binomial.',
                      ['binomial theorem', 'Pascal\'s triangle', 'coefficient'],
                      ['Summation notation']),
                    c('The counting principle',
                      'Independent choices multiply, which is the basis of all counting.',
                      ['counting principle', 'multiplication rule'],
                      ['The binomial theorem']),
                    c('Permutations and combinations',
                      'Permutations count ordered arrangements and combinations count unordered '
                      'selections.',
                      ['permutation', 'combination', 'factorial'],
                      ['The counting principle']),
                    c('Probability with combinatorics',
                      'Counting favourable and total outcomes gives a probability for equally '
                      'likely events.',
                      ['probability', 'favourable outcomes'],
                      ['Permutations and combinations']),
                ]},
            ]},
            {'unit': 'Matrices', 'prerequisites': ['Sequences, series and counting'], 'topics': [
                {'topic': 'Linear algebra foundations', 'concepts': [
                    c('Matrix notation and operations',
                      'Matrices are rectangular arrays, and addition and scalar multiplication act '
                      'entrywise.',
                      ['matrix', 'dimension', 'scalar multiplication'],
                      ['Probability with combinatorics']),
                    c('Matrix multiplication',
                      'Matrix multiplication combines rows of the first with columns of the second, '
                      'so order matters.',
                      ['matrix multiplication', 'row column'],
                      ['Matrix notation and operations']),
                    c('Determinants',
                      'A determinant is a number that reports whether a matrix is invertible.',
                      ['determinant', 'invertible', 'singular'],
                      ['Matrix multiplication']),
                    c('Inverse matrices',
                      'An inverse matrix undoes a linear transformation, and it exists only when '
                      'the determinant is non-zero.',
                      ['inverse matrix', 'identity matrix'],
                      ['Determinants']),
                    c('Solving systems with matrices',
                      'A linear system can be solved by matrix inverse or row reduction.',
                      ['matrix system', 'row reduction', 'augmented matrix'],
                      ['Inverse matrices']),
                ]},
            ]},
        ]},
    ],
}


# =================================================================== AP Calculus
AP_CALCULUS = {
    'id': 'ap_calculus',
    'title': 'AP Calculus',
    'subject': 'Mathematics',
    'subject_kind': 'mathematics',
    'expected_weeks': 36,
    'description': ('The AP Calculus AB and BC course framework: limits and continuity, '
                    'differentiation and its applications, integration and accumulation, '
                    'differential equations, applications of integration, and (BC) parametric, '
                    'polar, vector and series topics.'),
    'course': 'AP Calculus - Limits, Derivatives, Integrals and Series',
    'strands': [
        {'strand': 'Limits and Continuity', 'units': [
            {'unit': 'Limits', 'topics': [
                {'topic': 'Approaching a value', 'concepts': [
                    c('Estimating limits from graphs and tables',
                      'A limit describes the value a function approaches, which need not equal its '
                      'value at the point.',
                      ['limit', 'approach', 'graph']),
                    c('Defining limits and limit notation',
                      'The formal definition makes "approaches" precise and distinguishes one-sided '
                      'from two-sided limits.',
                      ['limit definition', 'one-sided limit', 'notation'],
                      ['Estimating limits from graphs and tables']),
                    c('Limit properties and algebraic techniques',
                      'Limits combine by sum, product and quotient, and factoring or rationalising '
                      'resolves indeterminate forms.',
                      ['limit laws', 'indeterminate form', 'factoring'],
                      ['Defining limits and limit notation']),
                    c('Limits at infinity',
                      'Limits at infinity describe end behaviour, including horizontal asymptotes.',
                      ['limits at infinity', 'end behaviour', 'horizontal asymptote'],
                      ['Limit properties and algebraic techniques']),
                    c('The squeeze theorem',
                      'If a function is trapped between two others with the same limit, it has that '
                      'limit too.',
                      ['squeeze theorem', 'bounding function'],
                      ['Limits at infinity']),
                ]},
            ]},
            {'unit': 'Continuity', 'prerequisites': ['Limits'], 'topics': [
                {'topic': 'Where functions hold together', 'concepts': [
                    c('Continuity at a point',
                      'A function is continuous when its limit exists, its value exists, and the '
                      'two agree.',
                      ['continuity', 'limit equals value'],
                      ['The squeeze theorem']),
                    c('Types of discontinuity',
                      'Removable, jump and infinite discontinuities differ in whether a limit '
                      'exists.',
                      ['removable discontinuity', 'jump', 'infinite'],
                      ['Continuity at a point']),
                    c('The intermediate value theorem',
                      'A continuous function on an interval takes every value between its endpoint '
                      'values.',
                      ['intermediate value theorem', 'continuous interval'],
                      ['Types of discontinuity']),
                ]},
            ]},
        ]},
        {'strand': 'Differentiation: Definition and Fundamental Properties', 'units': [
            {'unit': 'The derivative', 'prerequisites': ['Continuity'], 'topics': [
                {'topic': 'Rates and rules', 'concepts': [
                    c('Average and instantaneous rate of change',
                      'The average rate is a secant slope and the instantaneous rate is the limit '
                      'of secant slopes.',
                      ['average rate', 'instantaneous rate', 'secant'],
                      ['The intermediate value theorem']),
                    c('The derivative as a limit',
                      'The derivative is the limit of a difference quotient, which gives the slope '
                      'of the tangent line.',
                      ['derivative', 'difference quotient', 'tangent line'],
                      ['Average and instantaneous rate of change']),
                    c('Differentiability and continuity',
                      'Differentiable implies continuous, but continuity does not imply '
                      'differentiability.',
                      ['differentiability', 'continuity', 'corner'],
                      ['The derivative as a limit']),
                    c('The power rule',
                      'The derivative of x to the n is n times x to the n minus one.',
                      ['power rule', 'derivative'],
                      ['The derivative as a limit']),
                    c('Constant, sum and difference rules',
                      'Derivatives distribute over sums and differences, and a constant '
                      'differentiates to zero.',
                      ['sum rule', 'constant rule'],
                      ['The power rule']),
                    c('The product rule',
                      'The derivative of a product is the first times the derivative of the second '
                      'plus the second times the derivative of the first.',
                      ['product rule'],
                      ['Constant, sum and difference rules']),
                    c('The quotient rule',
                      'The derivative of a quotient follows a fixed numerator pattern over the '
                      'denominator squared.',
                      ['quotient rule'],
                      ['The product rule']),
                    c('Derivatives of trigonometric functions',
                      'Sine and cosine differentiate into each other with a sign change, and the '
                      'rest follow.',
                      ['trig derivative', 'sine', 'cosine'],
                      ['Constant, sum and difference rules']),
                    c('Higher-order derivatives',
                      'Repeated differentiation gives acceleration from velocity, and concavity '
                      'from slope.',
                      ['second derivative', 'higher order'],
                      ['The derivative as a limit']),
                    c('Tangent line approximation',
                      'The tangent line gives a local linear approximation of a function.',
                      ['linearisation', 'tangent line approximation'],
                      ['The derivative as a limit']),
                ]},
            ]},
        ]},
        {'strand': 'Differentiation: Composite, Implicit and Inverse Functions', 'units': [
            {'unit': 'Chain and implicit rules', 'prerequisites': ['The derivative'], 'topics': [
                {'topic': 'Composition and implicit relations', 'concepts': [
                    c('The chain rule',
                      'The derivative of a composition multiplies the outer derivative by the '
                      'inner derivative.',
                      ['chain rule', 'composite'],
                      ['Tangent line approximation']),
                    c('Implicit differentiation',
                      'Differentiating both sides of a relation and treating y as a function of x '
                      'gives dy by dx.',
                      ['implicit differentiation', 'dy/dx'],
                      ['The chain rule']),
                    c('Derivatives of inverse functions',
                      'The derivative of an inverse is the reciprocal of the original derivative at '
                      'the corresponding point.',
                      ['inverse function derivative', 'reciprocal'],
                      ['Implicit differentiation']),
                    c('Derivatives of exponential functions',
                      'The exponential function is its own derivative, and a base change brings '
                      'down a factor.',
                      ['exponential derivative', 'e^x'],
                      ['The chain rule']),
                    c('Derivatives of logarithmic functions',
                      'The natural logarithm differentiates to one over x, and the chain rule '
                      'extends it.',
                      ['logarithmic derivative', 'ln x'],
                      ['Derivatives of exponential functions']),
                    c('Derivatives of inverse trigonometric functions',
                      'Inverse trigonometric derivatives follow standard forms used in '
                      'integration.',
                      ['inverse trig derivative', 'arcsin'],
                      ['Derivatives of inverse functions']),
                    c('Logarithmic differentiation',
                      'Taking a logarithm first turns products and powers into sums, which '
                      'simplifies the derivative.',
                      ['logarithmic differentiation'],
                      ['Derivatives of logarithmic functions']),
                    c('Selecting differentiation procedures',
                      'Recognising the structure of an expression decides which rule applies.',
                      ['procedure selection', 'rule choice'],
                      ['Logarithmic differentiation']),
                ]},
            ]},
        ]},
        {'strand': 'Contextual Applications of Differentiation', 'units': [
            {'unit': 'Derivatives in context', 'prerequisites': ['Chain and implicit rules'], 'topics': [
                {'topic': 'Rates in the world', 'concepts': [
                    c('Interpreting derivatives in context',
                      'A derivative is a rate with units, and its sign reports direction of change.',
                      ['derivative meaning', 'units', 'rate'],
                      ['Selecting differentiation procedures']),
                    c('Straight-line motion',
                      'Position, velocity and acceleration are related by successive derivatives.',
                      ['position', 'velocity', 'acceleration'],
                      ['Interpreting derivatives in context']),
                    c('Related rates',
                      'When two quantities are linked, differentiating the relation in time '
                      'connects their rates.',
                      ['related rates', 'implicit differentiation'],
                      ['Straight-line motion']),
                    c('Local linearity and approximation',
                      'Near a point a differentiable function behaves like its tangent line.',
                      ['local linearity', 'approximation'],
                      ['Interpreting derivatives in context']),
                    c('L\'Hôpital\'s rule',
                      'Indeterminate limits of quotients can be evaluated by differentiating '
                      'numerator and denominator.',
                      ['L\'Hôpital', 'indeterminate form'],
                      ['Interpreting derivatives in context']),
                ]},
            ]},
        ]},
        {'strand': 'Analytical Applications of Differentiation', 'units': [
            {'unit': 'Shape of a graph', 'prerequisites': ['Derivatives in context'], 'topics': [
                {'topic': 'Extrema and concavity', 'concepts': [
                    c('The mean value theorem',
                      'Somewhere in an interval the instantaneous rate equals the average rate.',
                      ['mean value theorem', 'average rate'],
                      ['L\'Hôpital\'s rule']),
                    c('The extreme value theorem',
                      'A continuous function on a closed interval attains a maximum and a minimum.',
                      ['extreme value theorem', 'closed interval'],
                      ['The mean value theorem']),
                    c('Critical points',
                      'Critical points are where the derivative is zero or undefined, and they '
                      'candidate the extrema.',
                      ['critical point', 'stationary point'],
                      ['The extreme value theorem']),
                    c('Increasing and decreasing intervals',
                      'The sign of the derivative reports where a function rises or falls.',
                      ['increasing', 'decreasing', 'sign of derivative'],
                      ['Critical points']),
                    c('The first derivative test',
                      'A sign change of the derivative identifies a local maximum or minimum.',
                      ['first derivative test', 'local extremum'],
                      ['Increasing and decreasing intervals']),
                    c('Concavity and inflection points',
                      'The sign of the second derivative reports concavity and where it changes.',
                      ['concavity', 'inflection point', 'second derivative'],
                      ['The first derivative test']),
                    c('The second derivative test',
                      'The second derivative classifies a stationary point as a maximum or a '
                      'minimum.',
                      ['second derivative test', 'concave down'],
                      ['Concavity and inflection points']),
                    c('Optimisation problems',
                      'A constraint reduces a quantity to one variable, and the derivative locates '
                      'its optimum.',
                      ['optimisation', 'constraint'],
                      ['The second derivative test']),
                    c('Connecting graphs of f, f prime and f double prime',
                      'The signs and zeros of the first two derivatives describe the shape of the '
                      'function.',
                      ['graph relationships', 'derivative graphs'],
                      ['Concavity and inflection points']),
                ]},
            ]},
        ]},
        {'strand': 'Integration and Accumulation of Change', 'units': [
            {'unit': 'Accumulation', 'prerequisites': ['Shape of a graph'], 'topics': [
                {'topic': 'Adding up change', 'concepts': [
                    c('Riemann sums',
                      'A definite integral is the limit of sums of rectangular areas.',
                      ['Riemann sum', 'area approximation'],
                      ['Connecting graphs of f, f prime and f double prime']),
                    c('The definite integral as a limit',
                      'The integral is defined as a limit of Riemann sums, which makes accumulation '
                      'precise.',
                      ['definite integral', 'limit of sums'],
                      ['Riemann sums']),
                    c('The fundamental theorem of calculus',
                      'Differentiation and integration are inverse processes, which links area to '
                      'antiderivatives.',
                      ['fundamental theorem', 'antiderivative', 'accumulation'],
                      ['The definite integral as a limit']),
                    c('Antiderivatives and indefinite integrals',
                      'An antiderivative reverses differentiation, up to an additive constant.',
                      ['antiderivative', 'indefinite integral', 'constant of integration'],
                      ['The fundamental theorem of calculus']),
                    c('Properties of definite integrals',
                      'Integrals split, reverse sign and combine linearly, which simplifies '
                      'evaluation.',
                      ['integral properties', 'additivity'],
                      ['The fundamental theorem of calculus']),
                    c('Accumulation functions',
                      'An accumulation function\'s derivative is the integrand, which lets integrals '
                      'be differentiated.',
                      ['accumulation function', 'derivative of integral'],
                      ['The fundamental theorem of calculus']),
                    c('Integration by substitution',
                      'Substitution reverses the chain rule and simplifies many integrals.',
                      ['substitution', 'u-substitution'],
                      ['Antiderivatives and indefinite integrals']),
                    c('Integration by parts',
                      'Integration by parts reverses the product rule.',
                      ['integration by parts', 'product rule'],
                      ['Integration by substitution']),
                    c('Partial fractions',
                      'A rational integrand can be split into simpler fractions that integrate '
                      'directly.',
                      ['partial fractions', 'rational integrand'],
                      ['Integration by parts']),
                    c('Improper integrals',
                      'An integral over an infinite interval or with a singularity is defined by a '
                      'limit and may diverge.',
                      ['improper integral', 'convergence', 'diverge'],
                      ['Partial fractions']),
                ]},
            ]},
        ]},
        {'strand': 'Differential Equations', 'units': [
            {'unit': 'Modelling change', 'prerequisites': ['Accumulation'], 'topics': [
                {'topic': 'Equations involving a derivative', 'concepts': [
                    c('Modelling with differential equations',
                      'A differential equation states how a quantity changes in terms of the '
                      'quantity itself.',
                      ['differential equation', 'model'],
                      ['Improper integrals']),
                    c('Slope fields',
                      'A slope field draws the derivative at each point, which reveals solution '
                      'curves.',
                      ['slope field', 'direction field'],
                      ['Modelling with differential equations']),
                    c('Separation of variables',
                      'Separating the variables allows each side to be integrated independently.',
                      ['separation of variables', 'general solution'],
                      ['Slope fields']),
                    c('Exponential models',
                      'A rate proportional to the amount gives exponential growth or decay.',
                      ['exponential growth', 'decay', 'proportional rate'],
                      ['Separation of variables']),
                    c('Logistic models',
                      'A rate limited by a carrying capacity gives logistic growth.',
                      ['logistic growth', 'carrying capacity'],
                      ['Exponential models']),
                ]},
            ]},
        ]},
        {'strand': 'Applications of Integration', 'units': [
            {'unit': 'Using the integral', 'prerequisites': ['Modelling change'], 'topics': [
                {'topic': 'Area, volume and totals', 'concepts': [
                    c('Average value of a function',
                      'The average value is the integral over the interval divided by the interval '
                      'length.',
                      ['average value', 'mean value'],
                      ['Logistic models']),
                    c('Area between curves',
                      'Area between curves is the integral of the upper minus the lower function.',
                      ['area between curves', 'upper lower'],
                      ['Average value of a function']),
                    c('Volumes with known cross sections',
                      'Integrating the area of a cross section gives the volume of a solid.',
                      ['cross section', 'volume'],
                      ['Area between curves']),
                    c('Volumes of revolution: disk and washer',
                      'Rotating a region about an axis gives circular cross sections, with the '
                      'washer handling a gap.',
                      ['disk method', 'washer method', 'revolution'],
                      ['Volumes with known cross sections']),
                    c('Volumes of revolution: shell method',
                      'Cylindrical shells integrate along the axis perpendicular to the one used by '
                      'disks.',
                      ['shell method', 'cylindrical shell'],
                      ['Volumes of revolution: disk and washer']),
                    c('Arc length',
                      'Arc length integrates the length element derived from the Pythagorean '
                      'theorem.',
                      ['arc length', 'length element'],
                      ['Volumes of revolution: shell method']),
                    c('Accumulated change in context',
                      'The integral of a rate gives the total change in the underlying quantity.',
                      ['accumulated change', 'net change'],
                      ['Average value of a function']),
                ]},
            ]},
        ]},
        {'strand': 'Parametric, Polar and Vector Functions (BC)', 'units': [
            {'unit': 'Other coordinate systems', 'prerequisites': ['Using the integral'], 'topics': [
                {'topic': 'Curves beyond y equals f of x', 'concepts': [
                    c('Parametric equations and derivatives',
                      'Parametric curves describe x and y separately, and dy by dx is the ratio of '
                      'their derivatives.',
                      ['parametric', 'dy/dx', 'parameter'],
                      ['Arc length']),
                    c('Motion with parametric and vector functions',
                      'Velocity and acceleration become vector quantities with direction and '
                      'magnitude.',
                      ['vector function', 'velocity vector', 'speed'],
                      ['Parametric equations and derivatives']),
                    c('Polar coordinates',
                      'Polar coordinates locate a point by distance and angle, and they convert to '
                      'and from Cartesian.',
                      ['polar coordinates', 'conversion'],
                      ['Motion with parametric and vector functions']),
                    c('Area and arc length in polar coordinates',
                      'Polar area uses sectors rather than rectangles, which changes the integrand.',
                      ['polar area', 'polar arc length'],
                      ['Polar coordinates']),
                    c('Vector-valued functions',
                      'A vector-valued function traces a curve, and its derivative is a tangent '
                      'vector.',
                      ['vector-valued function', 'tangent vector'],
                      ['Motion with parametric and vector functions']),
                ]},
            ]},
        ]},
        {'strand': 'Infinite Sequences and Series (BC)', 'units': [
            {'unit': 'Convergence', 'prerequisites': ['Other coordinate systems'], 'topics': [
                {'topic': 'Infinite sums and tests', 'concepts': [
                    c('Convergence of sequences',
                      'A sequence converges when its terms approach a single finite limit.',
                      ['sequence', 'convergence', 'limit'],
                      ['Vector-valued functions']),
                    c('Introduction to series',
                      'A series is the sum of a sequence, and its partial sums decide convergence.',
                      ['series', 'partial sum'],
                      ['Convergence of sequences']),
                    c('Geometric series',
                      'A geometric series converges exactly when the common ratio is smaller than '
                      'one in size.',
                      ['geometric series', 'common ratio'],
                      ['Introduction to series']),
                    c('The nth-term test',
                      'If the terms do not approach zero, the series diverges, but the converse '
                      'does not hold.',
                      ['nth-term test', 'divergence test'],
                      ['Introduction to series']),
                    c('The integral test',
                      'A series and a related improper integral converge or diverge together.',
                      ['integral test', 'improper integral'],
                      ['The nth-term test']),
                    c('Comparison tests',
                      'Bounding a series by a known one decides convergence term by term.',
                      ['comparison test', 'limit comparison'],
                      ['The integral test']),
                    c('The alternating series test',
                      'Alternating terms that decrease to zero converge, with a bounded error.',
                      ['alternating series', 'error bound'],
                      ['Comparison tests']),
                    c('The ratio test',
                      'The ratio of successive terms decides absolute convergence, especially for '
                      'factorials and powers.',
                      ['ratio test', 'absolute convergence'],
                      ['Comparison tests']),
                    c('Absolute and conditional convergence',
                      'A series can converge while the series of absolute values diverges.',
                      ['absolute convergence', 'conditional convergence'],
                      ['The alternating series test']),
                ]},
            ]},
            {'unit': 'Representing functions as series', 'prerequisites': ['Convergence'], 'topics': [
                {'topic': 'Power and Taylor series', 'concepts': [
                    c('Taylor and Maclaurin series',
                      'A smooth function can be represented by a power series built from its '
                      'derivatives at a point.',
                      ['Taylor series', 'Maclaurin series', 'expansion'],
                      ['Absolute and conditional convergence']),
                    c('Power series and radius of convergence',
                      'A power series converges on an interval whose radius is found from the '
                      'ratio test.',
                      ['power series', 'radius of convergence', 'interval'],
                      ['Taylor and Maclaurin series']),
                    c('Approximating functions with polynomials',
                      'A Taylor polynomial approximates a function with a controllable error bound.',
                      ['Taylor polynomial', 'error bound', 'approximation'],
                      ['Power series and radius of convergence']),
                ]},
            ]},
        ]},
    ],
}


COURSES = [AP_MACROECONOMICS, AP_MICROECONOMICS, AP_BIOLOGY, AP_CHEMISTRY,
           ALGEBRA_2, AP_CALCULUS]


def seed_document(course: dict) -> dict:
    """The scope-and-sequence document the ingest pipeline reads.

    A concept's declared prerequisites are pruned to those inside its own unit. Unit-to-unit
    ordering is already expressed by the unit-level ``prerequisites`` bridge (the last concept
    of the named unit precedes the first concept of this one), so keeping the per-concept
    cross-unit links as well would chain the whole course into one line and leave the graph
    with a depth of roughly N. Pruning them keeps the gating structure branching: within-unit
    dependencies are authored, between-unit dependencies are bridged once per unit.
    """
    unit_of: dict[str, str] = {}
    for strand in course['strands']:
        for unit in strand['units']:
            for topic in unit['topics']:
                for concept in topic['concepts']:
                    unit_of[concept['title']] = unit['unit']

    strands = []
    for strand in course['strands']:
        units = []
        for unit in strand['units']:
            topics = []
            for topic in unit['topics']:
                concepts = []
                for concept in topic['concepts']:
                    entry = dict(concept)
                    if entry.get('prerequisites'):
                        kept = [p for p in entry['prerequisites']
                                if unit_of.get(p) == unit['unit']]
                        if kept:
                            entry['prerequisites'] = kept
                        else:
                            entry.pop('prerequisites')
                    concepts.append(entry)
                topics.append({**topic, 'concepts': concepts})
            units.append({**unit, 'topics': topics})
        strands.append({**strand, 'units': units})

    return {
        'course': course['course'],
        'licence': 'cc0',
        'source_url': '',
        'attribution': ATTRIBUTION,
        'scope': SCOPE,
        'description': course['description'],
        'expected_weeks': course['expected_weeks'],
        'strands': strands,
    }


def write_seed(course: dict) -> Path:
    path = SEED_DIR / f"{course['id']}.json"
    path.write_text(json.dumps(seed_document(course), indent=1, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return path


def build_pack(course: dict) -> Path:
    """Build the pack through the ordinary pipeline, then namespace every concept id.

    ``--sequence-within unit`` is deliberate. The default ``topic`` mode adds a *gating*
    prerequisite edge between every consecutive pair of concepts inside a topic, and
    these outlines group a whole unit under one topic, so the default turned each course
    into a single chain of depth ~N. With ``unit`` mode the within-unit ordering is
    recorded as teaching order (it sequences the course but does not gate it) and the
    gating structure is exactly the prerequisite intent authored above. The result is a
    branching graph whose depth is comparable to the shipped physics course.
    """
    out = PACK_DIR / f"{course['id']}.json"
    result = subprocess.run(
        [sys.executable, '-m', 'app.ingest.pipeline', 'build',
         '--seed', course['id'], '--name', course['id'], '--title', course['title'],
         '--sequence-within', 'unit', '--out', str(out)],
        cwd=str(BACKEND), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'pipeline build failed for {course["id"]}:\n{result.stdout}\n{result.stderr}')
    print(f'  {result.stdout.strip()}')

    pack = json.loads(out.read_text(encoding='utf-8'))
    prefix = f"{course['id']}_"
    room = MAX_ID - len(prefix)
    mapping = {node['id']: f'{prefix}{node["id"][:room]}' for node in pack['concepts']}
    for node in pack['concepts']:
        node['id'] = mapping[node['id']]
        node['prerequisites'] = [mapping.get(p, p) for p in node.get('prerequisites', [])]
        node['sequence_predecessors'] = [mapping.get(p, p) for p in
                                         node.get('sequence_predecessors', [])]
    pack['metadata']['id_namespace'] = {
        'prefix': prefix,
        'reason': ('Concept ids are global; the prefix keeps this course disjoint from the '
                   'shipped courses that share concept titles.'),
    }
    out.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return out


def main() -> int:
    for course in COURSES:
        print(f"building {course['id']} ({course['title']})")
        seed = write_seed(course)
        print(f'  wrote {seed.relative_to(BACKEND)}')
        pack = build_pack(course)
        print(f'  wrote {pack.relative_to(BACKEND)}')
    print('\ndone. Register the courses in app/courses.py and their references in '
          'app/ingest/policy.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
