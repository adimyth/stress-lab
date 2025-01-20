import asyncio
import statistics
import time
from collections import defaultdict
from typing import Dict, Literal, Optional, Union

import aiohttp
import numpy as np
from pydantic import HttpUrl
import plotly.graph_objects as go
from plotly.subplots import make_subplots


async def make_request(
    session: aiohttp.ClientSession,
    url: HttpUrl,
    method: Literal["GET", "POST"] = "GET",
    headers: Optional[Dict] = None,
    json_data: Optional[Dict] = None,
    start_timestamp: Optional[float] = None,
    ttfb_only: bool = True,
):
    """
    Make a single request to a given URL

    Args:
        session (aiohttp.ClientSession): Client session to use for the request
        url (HttpUrl): URL to test
        method (str): HTTP method to use (GET or POST)
        headers (Dict, optional): Headers to include in the request
        json_data (Dict, optional): JSON data to send with POST request
        start_timestamp (float, optional): Start time of the test
        ttfb_only (bool): Whether to only measure TTFB

    Returns:
        Dict: Statistics about the request
    """
    start = time.time()
    kwargs = {"headers": headers or {}}
    if method == "POST" and json_data:
        kwargs["json"] = json_data

    async with session.request(method, url, **kwargs) as response:
        ttfb = time.time() - start
        content = None if ttfb_only else await response.read()
        response.close()

        return {
            "ttfb": ttfb,
            "status": response.status,
            "timestamp": time.time() - (start_timestamp or start),
            "response_size": len(content) if content else None,
        }


async def load_test(
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
    Perform a load test on a given URL

    Args:
        url (HttpUrl): URL to test
        method (str): HTTP method to use (GET or POST)
        headers (Dict, optional): Headers to include in the request
        json_data (Dict, optional): JSON data to send with POST request
        requests_per_second (int): Number of requests to make per second
        num_times (int): Total number of times the request should be made at the given rate
        wait_time (float): Time to wait between requests
        ttfb_only (bool): Whether to only measure TTFB

    Returns:
        Dict: Statistics about the test
    """
    stats = defaultdict(list)
    responses_per_second = defaultdict(int)
    start_timestamp = time.time()

    connector = aiohttp.TCPConnector(force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        for _ in range(num_times):
            tasks = [
                make_request(
                    session, url, method, headers, json_data, start_timestamp, ttfb_only
                )
                for _ in range(requests_per_second)
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

            await asyncio.sleep(wait_time)

    stats["total_duration"] = time.time() - start_timestamp
    stats["responses_per_second"] = dict(responses_per_second)

    return stats


def print_statistics(stats):
    print(f"\nTest Summary:")
    print(f"Total Duration: {stats['total_duration']:.2f} seconds")
    print(f"Total Requests: {len(stats['ttfb'])}")
    print(f"Total Success: {stats['status'].count(200)}")
    print(f"Total Failures: {len(stats['ttfb']) - stats['status'].count(200)}")
    print(f"Requests per Second: {len(stats['ttfb']) / stats['total_duration']:.2f}")

    print(f"\nResponse Time Statistics:")
    print(f"Avg TTFB: {statistics.mean(stats['ttfb']):.3f}s")
    print(f"Max TTFB: {max(stats['ttfb']):.3f}s")
    print(f"Min TTFB: {min(stats['ttfb']):.3f}s")
    print(f"Median TTFB: {statistics.median(stats['ttfb']):.3f}s")

    ttfbs = np.array(stats["ttfb"])
    print(f"\nPercentiles:")
    print(f"90th Percentile TTFB: {np.percentile(ttfbs, 90):.3f}s")
    print(f"95th Percentile TTFB: {np.percentile(ttfbs, 95):.3f}s")
    print(f"99th Percentile TTFB: {np.percentile(ttfbs, 99):.3f}s")

    if stats.get("response_size"):
        print(f"\nResponse Size Statistics:")
        sizes = stats["response_size"]
        print(f"Avg Size: {statistics.mean(sizes)/1024:.2f} KB")
        print(f"Max Size: {max(sizes)/1024:.2f} KB")
        print(f"Min Size: {min(sizes)/1024:.2f} KB")
        print(f"Total Data: {sum(sizes)/1024/1024:.2f} MB")


def plot_load_test_results(stats, requests_per_second, num_times, wait_time, url=None):
    """
    Create an interactive visualization of load test results showing both
    request pattern and actual responses.

    Args:
        stats (dict): Statistics dictionary containing responses_per_second
        requests_per_second (int): Number of requests per second
        num_times (int): Number of times to send requests
        wait_time (float): Wait time between request batches
        url (str, optional): URL being tested
    """
    # Create figure with secondary y-axis
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            "<b>Actual Responses per Second</b>",
            "<b>Expected Request Pattern</b>",
        ),
        vertical_spacing=0.16,
    )

    # Plot 1: Actual Responses
    sorted_data = sorted(stats["responses_per_second"].items())
    timestamps = [point[0] for point in sorted_data]
    responses = [point[1] for point in sorted_data]

    # Calculate statistics
    avg_rps = sum(responses) / len(responses)
    max_rps = max(responses)
    min_rps = min(responses)

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
        row=1,
        col=1,
    )

    # Add average line for responses
    fig.add_trace(
        go.Scatter(
            x=[min(timestamps), max(timestamps)],
            y=[avg_rps, avg_rps],
            mode="lines",
            name=f"Average ({avg_rps:.1f})",
            line=dict(color="#e74c3c", dash="dash"),
            hovertemplate="<b>Average RPS</b>: %{y:.1f}<extra></extra>",
            legendgroup="actual",
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    # Plot 2: Expected Request Pattern
    x_steps = []
    y_steps = []

    for i in range(num_times):
        start_time = i * (1 + wait_time)
        end_time = start_time + 1

        x_steps.extend([start_time, start_time, end_time, end_time])
        y_steps.extend([0, requests_per_second, requests_per_second, 0])

    fig.add_trace(
        go.Scatter(
            x=x_steps,
            y=y_steps,
            mode="lines",
            name="Expected Pattern",
            line=dict(color="#2ecc71", width=2),
            hovertemplate=(
                "<b>Time</b>: %{x}s<br>" + "<b>RPS</b>: %{y}<br>" + "<extra></extra>"
            ),
            legendgroup="actual",
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    # Add target RPS line
    fig.add_trace(
        go.Scatter(
            x=[0, max(x_steps)],
            y=[requests_per_second, requests_per_second],
            mode="lines",
            name=f"Target RPS: {requests_per_second}",
            line=dict(color="#e74c3c", dash="dash"),
            hovertemplate="<b>Target RPS</b>: %{y}<extra></extra>",
            legendgroup="actual",
            showlegend=True,
        ),
        row=2,
        col=1,
    )

    # Update layout
    title_text = "<b>Load Test Analysis</b>"
    if url:
        title_text += f"<br><sub><b>{url}</b></sub>"

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
        height=900,
        hovermode="x unified",
    )

    # Update axes
    for i in range(1, 3):
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
            title_text="Responses per Second",
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(128, 128, 128, 0.2)",
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="rgba(128, 128, 128, 0.2)",
            row=i,
            col=1,
        )

    # Add test parameters
    params_text = (
        f"Test Parameters:<br>"
        f"Target RPS: {requests_per_second}<br>"
        f"Wait Time: {wait_time}s<br>"
        f"Total Batches: {num_times}<br><br>"
        f"Statistics:<br>"
        f"Max RPS: {max_rps}<br>"
        f"Min RPS: {min_rps}<br>"
        f"Avg RPS: {avg_rps:.1f}"
    )

    fig.add_annotation(
        x=1.15,  # Moved further right
        y=0.5,  # Centered vertically
        xref="paper",
        yref="paper",
        text=params_text,
        showarrow=False,
        font=dict(size=10),
        bgcolor="rgba(255, 255, 255, 0.8)",
        bordercolor="rgba(128, 128, 128, 0.5)",
        borderwidth=1,
        align="left",
    )

    fig.show()
