{% macro get_aqi_label(aqi_col) %}
  case
    when {{ aqi_col }} = 1 then 'Good'
    when {{ aqi_col }} = 2 then 'Fair'
    when {{ aqi_col }} = 3 then 'Moderate'
    when {{ aqi_col }} = 4 then 'Poor'
    when {{ aqi_col }} = 5 then 'Very Poor'
    else 'Unknown'
  end
{% endmacro %}
