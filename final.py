-- Revenue Tag COB total example
select proj_year, cg.title as channel,
       sum(num_claims),
       sum(prcgt.num_paper_claims)
from comp_engine_microservice_qa.revenue_gpi_tc prcgt
join artifactsdb_qa.channel_group cg
  on cg.id = prcgt.std_wo_cob_excl_none_id
where uw_req_id = '52B090B24E63467F81CB5ECA1235CDC7'
  and std_wo_cob_excl_none_id <> 5
  and prcgt.tag_coordination_of_benefits = 1
group by 1,2
order by 1,2;



-- Revenue Specialty (Pricing Recon) Exclusions (Before Exclusions)
select proj_year, cg.title as channel,
       sum(psgt.brand_claims)   brand_claims,
       sum(psgt.generic_claims) generic_claims,
       sum(psgt.total_claims)   claims
from comp_engine_microservice_output_qa.pnl_specialty_gpi_tc psgt
join artifactsdb_qa.channel_group cg
  on cg.id = psgt.channel_group_id
where scenario_id = 'B5FACBC09B854AB69940C7978C27BE26'
group by 1,2
order by 1,2;


-- Revenue (Pricing Recon) Exclusions (Before Exclusions)
select proj_year, cg.title as channel,
       sum(incl_claims) incl_claims,
       sum(excl_claims) excl_claims
from comp_engine_microservice_output_qa.pnl_revenue_cogs_gpi_tc prcgt
join artifactsdb_qa.channel_group cg
  on cg.id = prcgt.channel_group_id
where scenario_id = 'B5FACBC09B854AB69940C7978C27BE26'
group by 1,2
order by 1,2;

