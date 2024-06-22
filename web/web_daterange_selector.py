#!/usr/bin/env python3
import urllib.parse


def generate_date_filter_form(base_url, default_start_date="", default_end_date=""):
    # Parse base_url into base portion and parameter portion
    parsed_url = urllib.parse.urlparse(base_url)
    # base_portion = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    base_portion = base_url.split('?')[0]
    query_params = urllib.parse.parse_qs(parsed_url.query)
    # Remove 'start_date' and 'end_date' from query_params
    query_params = {
        k: v
        for k, v in query_params.items()
        if k.lower() not in ["start_date", "end_date"]
    }

    # Generate hidden input fields for parameters from base_url
    hidden_fields = "".join(
        f'<input type="hidden" name="{k}" value="{v[0]}">'
        for k, v in query_params.items()
    )

    # Generate HTML using f-string
    html = f"""
    <form action="{base_portion}" method="get" style="border: 1px solid black; display: inline-block; padding: 10px;">
        <label for="start_date">Start Date:</label>
        <input type="date" id="start_date" name="start_date" value="{default_start_date}" required pattern="[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}">

        <label for="end_date">End Date:</label>
        <input type="date" id="end_date" name="end_date" value="{default_end_date}" required pattern="[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}">

        <!-- Hidden fields for parameters from base_url -->
        {hidden_fields}

        <input type="submit" value="Filter by this date range">
    </form>
    """

    return html


def main():

    # Example base_url (replace with your actual base_url)
    base_url = "http://example.com/report?user=admin&role=user"

    # Default values or values from query parameters
    default_start_date = "2024-01-01"
    default_end_date = "2024-12-31"

    # Generate the date filter form HTML
    date_filter_html = generate_date_filter_form(
        base_url, default_start_date, default_end_date
    )

    # Print the HTML content
    print("Content-Type: text/html\n")
    print(
        f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>Date Range Filter</title>
    <style>
    form {{
        border: 1px solid black;
        display: inline-block;
        padding: 10px;
    }}
    </style>
    </head>
    <body>
    {date_filter_html}
    </body>
    </html>
    """
    )


if __name__ == "__main__":
    main()
