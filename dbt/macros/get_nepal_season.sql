{% macro get_nepal_season(ts_col) %}
  case
    when extract(month from {{ ts_col }}) in (12, 1, 2)  then 'Winter'
    when extract(month from {{ ts_col }}) in (3, 4, 5)    then 'Pre-monsoon'
    when extract(month from {{ ts_col }}) in (6, 7, 8, 9) then 'Monsoon'
    when extract(month from {{ ts_col }}) in (10, 11)     then 'Post-monsoon'
    else 'Unknown'
  end
{% endmacro %}
