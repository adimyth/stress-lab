import asyncio
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Literal, Optional

import aiohttp
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from pydantic import HttpUrl


class StressLab:
    def __init__(
        self,
        url: HttpUrl,
        method: Literal["GET", "POST"] = "GET",
        headers: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        requests_per_second: int = 10,
        num_times: int = 5,
        wait_time: float = 1,
        ttfb_only: bool = True,
    ):
        """
        Initialize StressLab with test parameters

        Args:
            url (HttpUrl): URL to test
            method (str): HTTP method to use (GET or POST)
            headers (Dict, optional): Headers to include in the request
            json_data (Dict, optional): JSON data to send with POST request
            requests_per_second (int): Number of requests to make per second
            num_times (int): Total number of times the request should be made at the given rate
            wait_time (float): Time to wait between requests
            ttfb_only (bool): Whether to only measure TTFB
        """
        self.url = url
        self.method = method
        self.headers = headers
        self.json_data = json_data
        self.requests_per_second = requests_per_second
        self.num_times = num_times
        self.wait_time = wait_time
        self.ttfb_only = ttfb_only
        self.stats = None

    async def make_request(
        self,
        session: aiohttp.ClientSession,
        start_timestamp: Optional[float] = None,
    ):
        """
        Make a single request to a given URL

        Args:
            session (aiohttp.ClientSession): Client session to use for the request
            start_timestamp (float, optional): Start time of the test

        Returns:
            Dict: Statistics about the request
        """
        start = time.time()
        kwargs = {"headers": self.headers or {}}
        if self.method == "POST" and self.json_data:
            kwargs["json"] = self.json_data

        async with session.request(self.method, self.url, **kwargs) as response:
            ttfb = time.time() - start
            content = None if self.ttfb_only else await response.read()
            response.close()

            return {
                "ttfb": ttfb,
                "status": response.status,
                "timestamp": time.time() - (start_timestamp or start),
                "response_size": len(content) if content else None,
            }

    async def run_test(self):
        """
        Run load test and collect statistics
        """
        stats = defaultdict(list)
        responses_per_second = defaultdict(int)
        start_timestamp = time.time()

        connector = aiohttp.TCPConnector(force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            for _ in range(self.num_times):
                tasks = [
                    self.make_request(session, start_timestamp)
                    for _ in range(self.requests_per_second)
                ]
                results = await asyncio.gather(*tasks)

                for result in results:
                    stats["ttfb"].append(result["ttfb"])
                    stats["status"].append(result["status"])
                    stats["timestamp"].append(result["timestamp"])
                    if result["response_size"] is not None:
                        stats["response_size"].append(result["response_size"])

                    second = int(result["timestamp"])
                    responses_per_second[second] += 1

                await asyncio.sleep(self.wait_time)

        stats["total_duration"] = time.time() - start_timestamp
        stats["responses_per_second"] = dict(responses_per_second)
        self.stats = stats

    def run(self):
        """Synchronous wrapper for run_test"""
        asyncio.run(self.run_test())

    def plot_results(self):
        """
        Create an interactive visualization of load test results -
        1. Test Summary Statistics
        2. Request Pattern
        3. Response Times
        4. Response per second
        """
        if not self.stats:
            print("No test results available. Run the test first.")
            return

        fig = make_subplots(
            rows=4,
            cols=1,
            subplot_titles=(
                "<b>Test Summary</b>",
                "<b>Request Pattern</b>",
                "<b>Avg Response Time</b>",
                "<b># Responses per second</b>",
            ),
            vertical_spacing=0.1,
            specs=[
                [{"type": "table"}],
                [{"type": "xy"}],
                [{"type": "xy"}],
                [{"type": "xy"}],
            ],
            row_heights=[0.3, 0.2, 0.25, 0.25],
        )

        # Plot 1: Test Summary
        table_headers = ["Metric", "Value"]
        table_values = [
            [
                "Total Duration",
                "Total Requests",
                "Total Success",
                "Total Failures",
                "Requests per Second",
                "Avg TTFB",
                "Max TTFB",
                "Min TTFB",
                "Median TTFB",
                "90th Percentile TTFB",
                "95th Percentile TTFB",
                "99th Percentile TTFB",
            ],
            [
                f"{self.stats['total_duration']:.2f}s",
                str(len(self.stats["ttfb"])),
                str(self.stats["status"].count(200)),
                str(len(self.stats["ttfb"]) - self.stats["status"].count(200)),
                f"{len(self.stats['ttfb']) / self.stats['total_duration']:.2f}",
                f"{statistics.mean(self.stats['ttfb']):.3f}s",
                f"{max(self.stats['ttfb']):.3f}s",
                f"{min(self.stats['ttfb']):.3f}s",
                f"{statistics.median(self.stats['ttfb']):.3f}s",
                f"{np.percentile(self.stats['ttfb'], 90):.3f}s",
                f"{np.percentile(self.stats['ttfb'], 95):.3f}s",
                f"{np.percentile(self.stats['ttfb'], 99):.3f}s",
            ],
        ]

        fig.add_trace(
            go.Table(
                header=dict(
                    values=table_headers,
                    font=dict(size=12, color="white"),
                    fill_color="#2c3e50",
                    align=["left", "right"],
                ),
                cells=dict(
                    values=table_values,
                    font=dict(size=11),
                    fill_color=["rgba(244, 244, 244, 0.8)", "rgba(244, 244, 244, 0.8)"],
                    align=["left", "right"],
                ),
                columnwidth=[0.7, 0.3],
            ),
            row=1,
            col=1,
        )

        # Plot 2: Request Pattern
        x_steps = []
        y_steps = []

        for i in range(self.num_times):
            start_time = i * (1 + self.wait_time)
            end_time = start_time + 1

            x_steps.extend([start_time, start_time, end_time, end_time])
            y_steps.extend([0, self.requests_per_second, self.requests_per_second, 0])

        fig.add_trace(
            go.Scatter(
                x=x_steps,
                y=y_steps,
                mode="lines",
                name="Request Pattern",
                line=dict(color="#2ecc71", width=2),
                hovertemplate=(
                    "<b>Time</b>: %{x}s<br>"
                    + "<b>RPS</b>: %{y}<br>"
                    + "<extra></extra>"
                ),
                legendgroup="actual",
                showlegend=True,
            ),
            row=2,
            col=1,
        )

        # Plot 3: Avg Response Time (TTFB)
        ttfb_data = list(zip(self.stats["timestamp"], self.stats["ttfb"]))
        ttfb_data.sort(key=lambda x: x[0])  # Sort by timestamp
        timestamps_ttfb = [point[0] for point in ttfb_data]
        ttfb_values = [point[1] for point in ttfb_data]
        avg_ttfb = sum(ttfb_values) / len(ttfb_values)

        fig.add_trace(
            go.Scatter(
                x=timestamps_ttfb,
                y=ttfb_values,
                mode="lines+markers",
                name="TTFB",
                line=dict(color="#9b59b6", width=2),
                marker=dict(
                    size=6,
                    symbol="circle",
                    color="#9b59b6",
                    line=dict(color="#8e44ad", width=1),
                ),
                legendgroup="ttfb",
                hovertemplate="<b>Time</b>: %{x}s<br><b>TTFB</b>: %{y:.3f}s<extra></extra>",
            ),
            row=3,
            col=1,
        )

        # Add average TTFB line
        fig.add_trace(
            go.Scatter(
                x=timestamps_ttfb,
                y=[avg_ttfb] * len(timestamps_ttfb),
                mode="lines",
                name=f"Avg Response Time ({avg_ttfb:.3f}s)",
                line=dict(color="#e74c3c", dash="dash"),
                legendgroup="ttfb",
                hovertemplate="<b>Average Response Time</b>: %{y:.3f}s<extra></extra>",
            ),
            row=3,
            col=1,
        )

        # Plot 4: Actual Responses
        sorted_data = sorted(self.stats["responses_per_second"].items())
        timestamps = [point[0] for point in sorted_data]
        responses = [point[1] for point in sorted_data]

        # Calculate statistics
        avg_rps = sum(responses) / len(responses)

        # Add response line with markers
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=responses,
                mode="lines+markers",
                name="Actual Responses",
                line=dict(color="#3498db", width=2),
                marker=dict(
                    size=8,
                    symbol="circle",
                    color="#3498db",
                    line=dict(color="#2980b9", width=1),
                ),
                hovertemplate=(
                    "<b>Time</b>: %{x}s<br>"
                    + "<b>Responses</b>: %{y}<br>"
                    + "<extra></extra>"
                ),
                legendgroup="actual",
                showlegend=True,
            ),
            row=4,
            col=1,
        )

        # Add average line for responses
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=[avg_rps] * len(timestamps),
                mode="lines",
                name=f"Average RPS ({avg_rps:.1f})",
                line=dict(color="#f39c12", dash="dash"),
                hovertemplate="<b>Average RPS</b>: %{y:.1f}<extra></extra>",
                legendgroup="actual",
                showlegend=True,
            ),
            row=4,
            col=1,
        )

        # Add plot title
        # Update layout
        title_text = "<b>Load Test Analysis</b>"
        title_text += f"<br><sub><b>{self.url}</b></sub>"

        fig.update_layout(
            title={
                "text": title_text,
                "y": 0.98,
                "x": 0.5,
                "xanchor": "center",
                "yanchor": "top",
            },
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                groupclick="toggleitem",
            ),
            plot_bgcolor="white",
            autosize=True,
            height=1600,
            hovermode="x unified",
        )

        # Update axes
        for i in range(2, 5):
            if i == 2:
                y_axis_title = "Requests per second"
            elif i == 3:
                y_axis_title = "Avg Response Time"
            elif i == 4:
                y_axis_title = "Responses per second"

            fig.update_xaxes(
                title_text="Time (seconds)",
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(128, 128, 128, 0.2)",
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor="rgba(128, 128, 128, 0.2)",
                row=i,
                col=1,
            )
            fig.update_yaxes(
                title_text=y_axis_title,
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(128, 128, 128, 0.2)",
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor="rgba(128, 128, 128, 0.2)",
                row=i,
                col=1,
            )

        # Remove gridlines for table subplot
        fig.update_xaxes(showgrid=False, showticklabels=False, row=1, col=1)
        fig.update_yaxes(showgrid=False, showticklabels=False, row=1, col=1)

        fig.show()
        return fig

    def save_results(self, fig=None, output_dir: str = "results"):
        """
        Save test results as PDF and PNG files

        Args:
            output_dir (str): Directory to save results in
        """
        if not self.stats:
            print("No test results available. Run the test first.")
            return

        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Generate timestamp for filenames
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base_filename = f"load_test_{timestamp}"

        # Save figures
        pio.write_image(fig, f"{output_dir}/{base_filename}.pdf", scale=2)
