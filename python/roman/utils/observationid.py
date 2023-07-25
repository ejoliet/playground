import pydantic

class ObservationID(pydantic.BaseModel):
  program_number: str
  execution_plan_number: str
  pass_number: str
  segment_number: str
  observation_number: str
  visit_number: str
  visit_file_group: str
  visit_file_sequence: str
  visit_file_activity: str
  exposure_id: str
  reserved: str

  @classmethod
  def from_string(cls, observation_id_string: str) -> "ObservationID":
    """Creates an ObservationID from a string."""
    visit_id, visit_file_statement, exposure_id = observation_id_string.split("_")
    visit_id_dict = {
      "program": visit_id[0:5],
      "exec_plan": visit_id[5:7],
      "pass": visit_id[7:10],
      "segment": visit_id[10:13],
      "observation": visit_id[13:16],
      "visit": visit_id[16:19],
    }

    visit_file_statement_dict = {
      "g": visit_file_statement[0:2],
      "s": visit_file_statement[2:3],
      "a": visit_file_statement[3:5],
    }

    exposure_id_dict = {
      "e": exposure_id[0:4],
    }

    return cls(
        program_number=visit_id_dict["program"],
        execution_plan_number=visit_id_dict["exec_plan"],
        pass_number=visit_id_dict["pass"],
        segment_number=visit_id_dict["segment"],
        observation_number=visit_id_dict["observation"],
        visit_number=visit_id_dict["visit"],
        visit_file_group=visit_file_statement_dict["g"],
        visit_file_sequence=visit_file_statement_dict["s"],
        visit_file_activity=visit_file_statement_dict["a"],
        exposure_id=exposure_id_dict["e"],
        reserved=exposure_id[4:],
    )

def main() -> None:
  observation_id_string = "1000122333421101123_23456_0987"
  observation_id = ObservationID.from_string(observation_id_string)
  json_string = json.dumps(observation_id.dict(), indent=2)
  print(json_string)

if __name__ == "__main__":
  main()
