from stress_lab import StressLab

json_data = {
    "name": "Apple MacBook Pro 16",
    "data": {
        "year": 2019,
        "price": 1849.99,
        "CPU model": "Intel Core i9",
        "Hard disk size": "1 TB",
    },
}


stress_test = StressLab(
    url="https://api.restful-api.dev/objects",
    method="POST",
    json_data=json_data,
    requests_per_second=2,
    num_times=3,
    wait_time=1,
    ttfb_only=True,
)


# Run the test
stress_test.run()

# Show results
fig = stress_test.plot_results()

# Save results
stress_test.save_results(fig=fig, output_dir="results")
