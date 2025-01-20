import asyncio
from stress_lab import load_test, print_statistics, plot_load_test_results

# URL, headers and request parameters
url = "https://api.restful-api.dev/objects"
method = "POST"

json_data = {
   "name": "Apple MacBook Pro 16",
   "data": {
      "year": 2019,
      "price": 1849.99,
      "CPU model": "Intel Core i9",
      "Hard disk size": "1 TB"
   }
}

# Test parameters
requests_per_second = 2
num_times = 3
wait_time = 1
ttfb_only = True



# Run the load test
stats = asyncio.run(
    load_test(
        url=url,
        method=method,
        json_data=json_data,
        requests_per_second=requests_per_second,
        num_times=num_times,
        wait_time=wait_time,
        ttfb_only=ttfb_only,
    )
)

# Print statistics
print_statistics(stats=stats)

# Plot the results
plot_load_test_results(
    url=url,
    stats=stats,
    requests_per_second=requests_per_second,
    num_times=num_times,
    wait_time=wait_time,
)
