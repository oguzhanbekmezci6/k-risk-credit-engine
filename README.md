Why I Built K-Risk

I developed K-Risk after graduation to gain practical experience and apply the theoretical knowledge I had learned to a real software project.

During the project, I worked on combining:

Statistics + Credit Risk + Financial Mathematics + Decision Theory + Python

in the same application.

The main purpose of K-Risk is not to claim that I recreated a real bank's internal credit system.

It is a project where I can demonstrate how I approach a complex problem, divide it into modules, translate mathematical concepts into code, test the results, and improve the model when I find inconsistencies.

<img width="1090" height="354" alt="image" src="https://github.com/user-attachments/assets/f35717f0-d086-4c2f-a4d4-a5947529f3b7" />


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

<img width="1113" height="253" alt="image" src="https://github.com/user-attachments/assets/dcf5c0f4-1c36-4df7-a549-968f4353b62f" />


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
