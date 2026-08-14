Why I Built K-Risk

I developed K-Risk as a post-graduation project to practise turning theoretical concepts into working software.

During the project, I worked on combining:

Statistics + Credit Risk + Financial Mathematics + Decision Theory + Python

in the same application.

The main purpose of K-Risk is not to claim that I recreated a real bank's internal credit system.

It is a project where I can demonstrate how I approach a complex problem, divide it into modules, translate mathematical concepts into code, test the results, and improve the model when I find inconsistencies.

<img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/fastapi/fastapi-original.svg" width="55"/> 


<img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" width="55"/>

 Limitations

K-Risk does not claim to provide:

Real banking credit decisions
Real customer data
Production PD/LGD models
Real institutional FTP curves
Regulatory capital calculations
ICAAP models
Live credit-bureau integration
Complete regulatory interpretation
Production model validation

K-Risk remains a learning, experimentation, and portfolio project.



credit.py

Main credit decision orchestrator.

Combines the results of the economic, risk, capital, decision-science, and policy modules.

loan_economics.py

Handles:

repayment schedules
loan balances
interest calculations
funding costs
expected cash flows
NPV
break-even pricing
credit_risk.py

Contains credit-risk analytics including:

PD / LGD / EAD
Monte Carlo simulation
Credit VaR
Expected Shortfall
stress testing
capital.py

Contains the project's pilot Economic Capital and risk-adjusted capital calculations.

science.py

Contains Bayesian and decision-theory calculations.

banking_policy.py

Keeps banking and policy controls separate from the mathematical risk engine.

 Technology Stack
 Python

The backend and analytical engine are primarily written in Python.

 Backend
-Python
FastAPI
Pydantic
Uvicorn
Starlette
- Database
SQLite
 Reporting
ReportLab
 Testing
Pytest
HTTPX
- Frontend
HTML
CSS
Vanilla JavaScript

Several financial and statistical calculations are implemented directly with Python's standard library, including:

math
random
statistics
sqlite3
