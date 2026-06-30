"""
reporting.py
============
ParaIQ Reporting & Analytics (Phase 4)

Aggregates firm-wide data into a unified dashboard endpoint.
Provides insights into matter profitability, time utilization,
and revenue pipeline.

Features:
  - Matter status breakdown
  - Total billable hours tracked
  - Outstanding AR (Accounts Receivable)
  - Recent client intake count
"""

import logging
from typing import Dict, Any
from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

def get_firm_dashboard(firm_id: str) -> Dict[str, Any]:
    """
    Gathers aggregate metrics for the firm dashboard.
    """
    dashboard = {
        "matters": {},
        "billing": {},
        "time_tracking": {},
        "intake": {}
    }
    
    try:
        with get_conn(firm_id) as conn:
            # 1. Matter Statistics
            try:
                matters_stats = conn.execute("""
                    SELECT status, COUNT(*) 
                    FROM matters 
                    GROUP BY status;
                """).fetchall()
                dashboard["matters"]["by_status"] = {row[0]: row[1] for row in matters_stats} if matters_stats else {}
            except Exception as e:
                logger.warning(f"Could not fetch matters stats: {e}")
                
            # 2. Billing Statistics
            try:
                billing_stats = conn.execute("""
                    SELECT 
                        COUNT(*) as total_invoices,
                        COALESCE(SUM(total_amount), 0) as total_billed,
                        COALESCE(SUM(amount_paid), 0) as total_collected,
                        COALESCE(SUM(total_amount - amount_paid), 0) as outstanding_ar
                    FROM invoices;
                """).fetchone()
                if billing_stats:
                    dashboard["billing"] = {
                        "total_invoices": billing_stats[0],
                        "total_billed": float(billing_stats[1]),
                        "total_collected": float(billing_stats[2]),
                        "outstanding_ar": float(billing_stats[3])
                    }
            except Exception as e:
                logger.warning(f"Could not fetch billing stats: {e}")
                
            # 3. Time Tracking Statistics
            try:
                time_stats = conn.execute("""
                    SELECT 
                        COUNT(*) as total_entries,
                        COALESCE(SUM(duration_minutes), 0) as total_minutes
                    FROM time_entries;
                """).fetchone()
                if time_stats:
                    total_hrs = float(time_stats[1] / 60.0)
                    dashboard["time_tracking"] = {
                        "total_entries": time_stats[0],
                        "total_hours": round(total_hrs, 2)
                    }
            except Exception as e:
                logger.warning(f"Could not fetch time stats: {e}")

            # 4. Intake/Lead Statistics (Assuming a leads table exists or using client count)
            try:
                client_stats = conn.execute("""
                    SELECT COUNT(*) FROM clients;
                """).fetchone()
                dashboard["intake"]["total_clients"] = client_stats[0] if client_stats else 0
            except Exception as e:
                logger.warning(f"Could not fetch client stats: {e}")

        return {"success": True, "dashboard": dashboard}
        
    except Exception as e:
        logger.error(f"Error generating firm dashboard: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
