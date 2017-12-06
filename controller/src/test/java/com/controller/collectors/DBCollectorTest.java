package com.controller.collectors;

import com.controller.util.ValidationUtils;
import com.github.fge.jsonschema.core.exceptions.ProcessingException;
import org.junit.Test;

import java.io.File;
import java.io.IOException;

/**
 *
 */
public class DBCollectorTest {
    @Test
    public void outputTest() throws IOException, ProcessingException {
        File schemaFile = new File("/src/main/java/com/controller/schema.json");
        File jsonFile = new File("/output/mysql/knobs.json");

        if (ValidationUtils.isJsonValid(schemaFile, jsonFile)){
            System.out.println("Valid!");
        }else{
            System.out.println("NOT valid!");
        }

    }


}